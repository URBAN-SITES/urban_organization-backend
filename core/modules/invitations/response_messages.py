from django.utils.translation import gettext_lazy as _

MSG_INVITE_INVALID = _("Invalid, expired or already used invitation.")
MSG_INVITE_ALREADY_PENDING = _("This e-mail already has a pending invitation.")
MSG_INVITE_ALREADY_MEMBER = _("This e-mail already belongs to a member.")
MSG_INVITE_NOT_PENDING = _("Only pending invitations can be revoked.")
MSG_INVITE_RECEIVED = _("You were invited to an organization")
MSG_INVITE_ACCEPTED = _("Your organization invitation was accepted")
MSG_INVITE_USED = _("This invitation was already accepted or revoked.")
MSG_INVITE_EXPIRED = _("This invitation has expired. Ask for a new one.")
MSG_INVITE_WRONG_ACCOUNT = _("This invitation was sent to another e-mail address.")
