from django.utils.translation import gettext_lazy as _

MSG_SECTOR_ROLE_REQUIRED = _("You do not have permission to do this in this sector.")
MSG_SECTOR_USER_NOT_IN_ORGANIZATION = _(
    "This user is not a member of the organization."
)
MSG_SECTOR_ALREADY_MEMBER = _("This user is already a sector participant.")
MSG_SECTOR_TEAM_INVALID = _("This team does not belong to the sector's organization.")
MSG_SECTOR_TEAM_ALREADY_LINKED = _("This team is already linked to the sector.")
MSG_STATUS_NAME_TAKEN = _("This sector already has a status with this name.")
MSG_STATUS_HAS_TASKS = _("Move or delete the tasks of this status first.")
MSG_STATUS_LAST_DONE = _("A sector needs at least one status in the done category.")
MSG_STATUS_WIP_LIMIT = _("This status reached its WIP limit.")
MSG_STATUS_INVALID = _("This status belongs to another sector.")
MSG_TASK_ASSIGNEE_INVALID = _("The assignee must be a participant of the sector.")
MSG_TASK_PARENT_INVALID = _("The parent task must be in the same sector.")
MSG_TASK_ASSIGNED = _("You were assigned to a task")
MSG_TASK_COMMENTED = _("New comment on your task")
MSG_TASK_STATUS_CHANGED = _("Your task changed status")
MSG_CALENDAR_RANGE_INVALID = _(
    "The end date must not be before the start date and the range is limited to 62 days."
)
