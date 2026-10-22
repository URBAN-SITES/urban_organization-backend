from django.utils.translation import gettext_lazy as _

# =====================================
# Success messages, used in views/ and inline_serializers of response_serializers.py
# =====================================
MSG_CODE_SENT = _("If the e-mail exists, a code was sent.")
MSG_CODE_VALID = _("Code is valid.")
MSG_USER_CREATED = _("User successfully created.")
MSG_PASWORD_RESET = _("Password has been reset successfully.")
MSG_EMAIL_CHANGED = _("E-mail successfully changed.")
MSG_USER_DEACTIVATED = _("Your account has been successfully deactivated.")
MSG_USER_REVOKED_ALL_SESSIONS = _("All active sessions have been revoked.")
MSG_LOGIN_SUCCESSFUL = _("Login successful.")
MSG_LOGOUT_SUCCESSFUL = _("Logout successful.")
MSG_USER_SESSION_DEACTIVATED = _("The session has been deactivated.")
MSG_REFRESH_TOKENS_SUCCESSFUL = _("Refresh tokens successful.")

# =====================================
# Fail messages, used in services/ and inline_serializers of response_serializers.py
# =====================================
MSG_SERVICE_UNAVAILABLE = _("Service temporarily unavailable.")
MSG_CODE_INVALID = _("Invalid or expired verification code.")
MSG_EMAIL_ALREADY_EXIST = _("This account is already active.")
MSG_USER_SESSION_NOT_FOUND = _("Session not found.")
MSG_USER_NOT_FOUND = _("User not found.")
MSG_CANNOT_DEACTIVATE_CURRENT_SESSION = _(
    "You cannot deactivate your current session from here. Please use logout instead."
)
MSG_NO_REFRESH_TOKEN_PROVIDED = _("No refresh token provided.")
MSG_INVALID_OR_EXPIRED_REFRESH_TOKEN = _("Invalid or expired refresh token.")
MSG_SESSION_REVOKED_OR_INACTIVE = _("Session revoked or inactive.")
MSG_GOOGLE_CREDENTIAL_INVALID = _("Invalid Google credential.")
MSG_GOOGLE_EMAIL_NOT_VERIFIED = _("Google e-mail is not verified.")
