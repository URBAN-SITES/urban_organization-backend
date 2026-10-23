from django.utils.translation import gettext_lazy as _

MSG_CHAT_USER_NOT_IN_ORGANIZATION = _("This user is not a member of the organization.")
MSG_CHAT_DIRECT_WITH_SELF = _("You cannot start a conversation with yourself.")
MSG_CHAT_REPLY_INVALID = _("The replied message is not in this channel.")
MSG_CHAT_AFTER_INVALID = _("`after` must be an ISO 8601 date-time.")
MSG_CHAT_MESSAGE_FORBIDDEN = _("You can only change your own messages.")
MSG_CHAT_MESSAGE_DELETED = _("This message was deleted.")
MSG_CHAT_TEAMS_INVALID = _("Pick at least two active teams of this organization.")
MSG_CHAT_TEAMS_NOT_ALLOWED = _(
    "You must belong to one of the teams to create this channel."
)
MSG_CHAT_EMPTY = _("Write a message or attach a file.")
MSG_CHAT_TASK_INVALID = _("You cannot cite this task.")
