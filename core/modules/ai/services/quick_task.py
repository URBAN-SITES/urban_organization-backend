"""Create a task from natural-language parts: names resolved and notes made by the server."""

import unicodedata
import uuid

from rest_framework.exceptions import ValidationError

from core.modules.ai.response_messages import (
    MSG_AI_NOTE_PEOPLE,
    MSG_AI_NOTE_TIME,
    MSG_AI_NOTE_TIME_NO_DATE,
    MSG_AI_PERSON_AMBIGUOUS,
    MSG_AI_PERSON_NO_ACCESS,
    MSG_AI_PERSON_NOT_FOUND,
)
from core.modules.kanban.serializers.task import TaskSerializer
from core.modules.kanban.services.sector import Role, SectorService
from core.modules.kanban.services.task import TaskService
from core.modules.organizations.models.organization import OrganizationMember
from core.modules.organizations.services.organization import OrganizationService

FILLER_WORDS = {"usuario", "user", "o", "a", "do", "da"}


def fold(text):
    """Lowercase without accents, so 'Nicolé' matches 'nicole'."""
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if not unicodedata.combining(c)).casefold().strip()


def words(user):
    return [*fold(user.name).split(), fold(user.email.split("@")[0])]


def find_person(query, users):
    tokens = [t for t in fold(query).split() if t not in FILLER_WORDS]
    if not tokens:
        return []
    joined = " ".join(tokens)
    # Only the full name or full e-mail is exact; a first name must stay ambiguous.
    exact = [u for u in users if joined in (fold(u.name), fold(u.email))]
    return exact or [
        u for u in users if all(any(w.startswith(t) for w in words(u)) for t in tokens)
    ]


def sector_people(sector):
    """Active organization members who can actually be assigned in this sector."""
    members = OrganizationMember.objects.filter(
        organization_id=sector.organization_id, user__is_active=True
    ).select_related("user")
    everyone = [m.user for m in members]
    return everyone, [u for u in everyone if SectorService.effective_role(u, sector)]


def match_person(name, everyone, in_sector):
    """(user, None) when exactly one person fits, else (None, (reason, candidates))."""
    matches = find_person(name, in_sector)
    if len(matches) == 1:
        return matches[0], None
    if matches:
        return None, ("ambiguous", matches)
    return None, ("no_access" if find_person(name, everyone) else "not_found", [])


def resolve_people(sector, names):
    everyone, in_sector = sector_people(sector)
    resolved = []
    for name in names:
        person, problem = match_person(name, everyone, in_sector)
        if person is None:
            reason, matches = problem
            if reason == "ambiguous":
                options = ", ".join(sorted(u.name or u.email for u in matches))
                text = str(MSG_AI_PERSON_AMBIGUOUS) % {"name": name, "options": options}
            else:
                message = (
                    MSG_AI_PERSON_NO_ACCESS
                    if reason == "no_access"
                    else MSG_AI_PERSON_NOT_FOUND
                )
                text = str(message) % {"name": name}
            raise ValidationError({"assignees": text})
        if person not in resolved:
            resolved.append(person)
    return resolved


def people_by_ids(sector, ids):
    _everyone, in_sector = sector_people(sector)
    by_id = {str(u.pk): u for u in in_sector}
    people = []
    for pk in ids:
        person = by_id.get(str(pk))
        if person is None:
            raise ValidationError({"assignee_ids": str(MSG_AI_PERSON_NO_ACCESS) % {"name": pk}})
        if person not in people:
            people.append(person)
    return people


def person_dict(user):
    return {"id": str(user.pk), "name": user.name or user.email}


def build_task(user, sector_id, people, *, title, description, priority, due_date, due_time):
    """The single place that turns a confirmed draft into a Task (and its notes)."""
    lines, notes = [description.strip()] if description.strip() else [], []
    if due_time:
        clock = f"{due_time:%H:%M}"
        when = f"{due_date:%d/%m/%Y} às {clock}" if due_date else f"às {clock}"
        lines.append(f"Horário: {when}.")
        note = MSG_AI_NOTE_TIME if due_date else MSG_AI_NOTE_TIME_NO_DATE
        notes.append(str(note) % {"time": clock})
    if len(people) > 1:
        others = ", ".join(p.name or p.email for p in people[1:])
        lines.append(f"Também envolvidos: {others}.")
        notes.append(
            str(MSG_AI_NOTE_PEOPLE)
            % {"first": people[0].name or people[0].email, "others": others}
        )
    data = {"title": title, "description": "\n\n".join(lines), "priority": priority}
    if due_date:
        data["due_date"] = due_date
    if people:
        data["assignee"] = people[0]
    task = TaskService.create(user, sector_id, data)
    return {**TaskSerializer(task).data, "notes": notes}


def quick_create(
    user,
    sector_id,
    *,
    title,
    description="",
    priority="medium",
    due_date=None,
    due_time=None,
    assignees=(),
):
    sector, _role = SectorService.get_sector(user, sector_id, Role.EDITOR)
    people = resolve_people(sector, assignees)
    return build_task(
        user, sector_id, people, title=title, description=description,
        priority=priority, due_date=due_date, due_time=due_time,
    )


def create_from_draft(
    user,
    sector_id,
    *,
    title,
    description="",
    priority="medium",
    due_date=None,
    due_time=None,
    assignee_ids=(),
):
    """Confirmed draft: people arrive as IDs chosen in the UI and are re-checked."""
    sector, _role = SectorService.get_sector(user, sector_id, Role.EDITOR)
    return build_task(
        user, sector_id, people_by_ids(sector, assignee_ids), title=title,
        description=description, priority=priority, due_date=due_date, due_time=due_time,
    )


def editable_sectors(user):
    """Sectors where the user may create tasks, across their organizations."""
    sectors = []
    for org in OrganizationService.list_for(user):
        for sector in SectorService.list_for(user, org.pk):
            if SectorService.effective_role(user, sector) in (Role.EDITOR, Role.MANAGER):
                sectors.append(
                    {
                        "id": str(sector.pk),
                        "name": sector.name,
                        "organization_name": org.name,
                    }
                )
    return sectors[:30]


def draft_task(
    user,
    *,
    title,
    description="",
    priority="medium",
    due_date=None,
    due_time=None,
    assignees=(),
    sector_id=None,
):
    """Prepare a task for confirmation. Nothing is written; problems become choices."""
    options = editable_sectors(user)
    if sector_id is None and len(options) == 1:
        sector_id = options[0]["id"]
    sector, people_options, resolved, unresolved = None, [], [], []
    if sector_id is not None:
        sector, _role = SectorService.get_sector(user, sector_id, Role.EDITOR)
        everyone, in_sector = sector_people(sector)
        people_options = [person_dict(u) for u in in_sector]
        for name in assignees:
            person, problem = match_person(name, everyone, in_sector)
            if person is not None:
                if person_dict(person) not in resolved:
                    resolved.append(person_dict(person))
                continue
            reason, matches = problem
            unresolved.append(
                {
                    "query": name,
                    "reason": reason,
                    "candidates": [person_dict(u) for u in matches],
                }
            )
    elif assignees:
        unresolved = [{"query": n, "reason": "sector_needed", "candidates": []} for n in assignees]
    missing = [
        label
        for label, absent in (
            ("sector", sector is None),
            ("due_date", due_date is None),
            ("assignees", not resolved and not unresolved),
        )
        if absent
    ]
    return {
        "kind": "task_draft",
        "request_id": str(uuid.uuid4()),
        "sector": {"id": str(sector.pk), "name": sector.name} if sector else None,
        "sector_options": options,
        "title": title,
        "description": description,
        "priority": priority,
        "due_date": due_date.isoformat() if due_date else None,
        "due_time": f"{due_time:%H:%M}" if due_time else None,
        "assignees": resolved,
        "unresolved": unresolved,
        "people_options": people_options,
        "missing": missing,
    }
