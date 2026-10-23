import json
import uuid

import requests
from rest_framework.exceptions import NotFound, ValidationError

from core.models.user import User
from core.modules.calendar_sync.response_messages import (
    MSG_DRIVE_FORBIDDEN,
    MSG_DRIVE_NOT_FOUND,
    MSG_DRIVE_TOO_BIG,
    MSG_GOOGLE_NOT_CONNECTED,
)
from core.modules.calendar_sync.services.google import (
    SCOPE_DRIVE,
    TIMEOUT,
    GoogleCalendarService,
    GoogleUnavailable,
)
from core.modules.kanban.models.resource_link import ResourceLink
from core.modules.kanban.services.sector import Role
from core.modules.kanban.services.task import TaskService

DRIVE_API = "https://www.googleapis.com/drive/v3"
UPLOAD_API = "https://www.googleapis.com/upload/drive/v3/files"
FOLDER_NAME = "Inceptum"
FOLDER_MIME = "application/vnd.google-apps.folder"
FILE_FIELDS = "id,name,mimeType,size,webViewLink,modifiedTime"
MAX_BYTES = 10 * 1024 * 1024


def _quote(text: str) -> str:
    """Escapes a value inside a Drive query string ('...')."""
    return text.replace("\\", "\\\\").replace("'", "\\'")


def _describe(item: dict) -> dict:
    return {
        "id": item["id"],
        "name": item.get("name", ""),
        "mime_type": item.get("mimeType", ""),
        "size_bytes": int(item["size"]) if item.get("size") else None,
        "web_view_link": item.get("webViewLink", ""),
        "modified_at": item.get("modifiedTime"),
    }


class GoogleDriveService:
    """Files kept in the user's own Drive, inside an "Inceptum" folder.

    Uses the drive.file scope: Google only exposes files this app created, so the
    app never sees the rest of the person's Drive.
    """

    @staticmethod
    def upload(user: User, file, share_link: bool = False) -> dict:
        if file.size > MAX_BYTES:
            raise ValidationError(MSG_DRIVE_TOO_BIG)
        folder = GoogleDriveService._folder_id(user, create=True)
        boundary = uuid.uuid4().hex
        metadata = json.dumps({"name": file.name[:255], "parents": [folder]})
        mime = file.content_type or "application/octet-stream"
        body = b"".join(
            [
                f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n".encode(),
                metadata.encode(),
                f"\r\n--{boundary}\r\nContent-Type: {mime}\r\n\r\n".encode(),
                file.read(),
                f"\r\n--{boundary}--".encode(),
            ]
        )
        created = GoogleDriveService._call(
            user,
            "POST",
            UPLOAD_API,
            params={"uploadType": "multipart", "fields": FILE_FIELDS},
            headers={"Content-Type": f"multipart/related; boundary={boundary}"},
            data=body,
        ).json()
        if share_link:  # explicit opt-in: anyone holding the link can read it
            GoogleDriveService._call(
                user,
                "POST",
                f"{DRIVE_API}/files/{created['id']}/permissions",
                json={"type": "anyone", "role": "reader"},
            )
        return {**_describe(created), "shared_with_link": share_link}

    @staticmethod
    def list_files(user: User, search: str = "") -> list[dict]:
        folder = GoogleDriveService._folder_id(user, create=False)
        if folder is None:
            return []
        query = f"'{folder}' in parents and trashed = false"
        if search:
            query += f" and name contains '{_quote(search)}'"
        response = GoogleDriveService._call(
            user,
            "GET",
            f"{DRIVE_API}/files",
            params={
                "q": query,
                "fields": f"files({FILE_FIELDS})",
                "orderBy": "modifiedTime desc",
                "pageSize": 25,
            },
        )
        return [_describe(item) for item in response.json().get("files", [])]

    @staticmethod
    def get_file(user: User, file_id: str) -> dict:
        response = GoogleDriveService._call(
            user,
            "GET",
            f"{DRIVE_API}/files/{file_id}",
            params={"fields": FILE_FIELDS},
        )
        return _describe(response.json())

    @staticmethod
    def attach_to_task(user: User, task_id, file_id: str) -> ResourceLink:
        """Adds a Drive file to a task as a link. The task permission is checked first."""
        task, _sector, _role = TaskService.get_task(user, task_id, Role.EDITOR)
        return GoogleDriveService._link(
            user, task, GoogleDriveService.get_file(user, file_id)
        )

    @staticmethod
    def upload_to_task(user: User, task_id, file, share_link: bool = False):
        task, _sector, _role = TaskService.get_task(user, task_id, Role.EDITOR)
        uploaded = GoogleDriveService.upload(user, file, share_link)
        return uploaded, GoogleDriveService._link(user, task, uploaded)

    # helpers ------------------------------------------------------------

    @staticmethod
    def _link(user: User, task, described: dict) -> ResourceLink:
        if not described["web_view_link"]:
            raise GoogleUnavailable()
        return ResourceLink.objects.create(
            task=task,
            created_by=user,
            title=described["name"][:255],
            url=described["web_view_link"],
        )

    @staticmethod
    def _folder_id(user: User, create: bool) -> str | None:
        query = (
            f"name = '{FOLDER_NAME}' and mimeType = '{FOLDER_MIME}' and trashed = false"
        )
        found = (
            GoogleDriveService._call(
                user,
                "GET",
                f"{DRIVE_API}/files",
                params={"q": query, "fields": "files(id)", "pageSize": 1},
            )
            .json()
            .get("files", [])
        )
        if found:
            return found[0]["id"]
        if not create:
            return None
        return GoogleDriveService._call(
            user,
            "POST",
            f"{DRIVE_API}/files",
            params={"fields": "id"},
            json={"name": FOLDER_NAME, "mimeType": FOLDER_MIME},
        ).json()["id"]

    @staticmethod
    def _call(user: User, method: str, url: str, headers=None, **kwargs):
        token = GoogleCalendarService.access_token(user, SCOPE_DRIVE)
        try:
            response = requests.request(
                method,
                url,
                headers={"Authorization": f"Bearer {token}", **(headers or {})},
                timeout=TIMEOUT,
                **kwargs,
            )
        except requests.RequestException:
            raise GoogleUnavailable()
        if response.status_code == 401:  # the token itself was rejected
            GoogleCalendarService.mark_revoked(user)
            raise ValidationError(MSG_GOOGLE_NOT_CONNECTED)
        if response.status_code == 403:  # this file/operation is not allowed
            raise ValidationError(MSG_DRIVE_FORBIDDEN)
        if response.status_code == 404:
            raise NotFound(MSG_DRIVE_NOT_FOUND)
        if not response.ok:
            raise GoogleUnavailable()
        return response
