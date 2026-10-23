from django.utils.translation import gettext_lazy as _

MSG_GOOGLE_NOT_CONFIGURED = _("Google integration is not configured on the server.")
MSG_GOOGLE_STATE_INVALID = _("Invalid or expired authorization state.")
MSG_GOOGLE_CODE_REJECTED = _("Google rejected the authorization code.")
MSG_GOOGLE_NOT_CONNECTED = _("Connect your Google account first.")
MSG_GOOGLE_UNAVAILABLE = _("Google is unavailable, try again later.")
MSG_GOOGLE_DISCONNECTED = _("Google account disconnected.")
MSG_GOOGLE_SCOPE_MISSING = _(
    "Reconnect your Google account and allow access to Google Drive."
)
MSG_DRIVE_TOO_BIG = _("The file can have at most 10 MB.")
MSG_DRIVE_FORBIDDEN = _("Google denied access to this file.")
MSG_DRIVE_NOT_FOUND = _("File not found in your Google Drive.")
MSG_CALENDAR_NO_DUE_DATE = _(
    "Set a due date on the task before adding it to Google Calendar."
)
