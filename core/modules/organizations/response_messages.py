from django.utils.translation import gettext_lazy as _

MSG_ORGANIZATION_ROLE_REQUIRED = _(
    "You do not have permission to do this in this organization."
)
MSG_ORGANIZATION_PERSONAL_PROTECTED = _("A personal organization cannot be deleted.")
MSG_ORGANIZATION_OWNER_PROTECTED = _(
    "The owner role cannot be assigned, changed or removed here."
)
MSG_ORGANIZATION_USER_NOT_FOUND = _("No active user with this e-mail.")
MSG_ORGANIZATION_ALREADY_MEMBER = _("This user is already a member.")
