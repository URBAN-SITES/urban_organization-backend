from django.utils.translation import gettext_lazy as _

MSG_GITHUB_NOT_CONFIGURED = _("GitHub integration is not configured on the server.")
MSG_GITHUB_UNAVAILABLE = _("GitHub is unavailable, try again later.")
MSG_GITHUB_RATE_LIMITED = _("GitHub API rate limit reached, try again later.")
MSG_GITHUB_NOT_CONNECTED = _("Connect your GitHub account again.")
MSG_GITHUB_FORBIDDEN = _("The GitHub App lacks permission for this repository.")
MSG_GITHUB_STATE_INVALID = _("Invalid or expired authorization state.")
MSG_GITHUB_CODE_REJECTED = _("GitHub rejected the authorization code.")
MSG_GITHUB_NO_EMAIL = _("Your GitHub account has no verified e-mail address.")
MSG_GITHUB_ACCOUNT_INACTIVE = _("This account is disabled.")
MSG_GITHUB_IDENTITY_TAKEN = _("This GitHub account is linked to another user.")
MSG_GITHUB_LOGIN_REQUIRED = _("Log in before connecting GitHub.")
MSG_GITHUB_REPO_NOT_AUTHORIZED = _(
    "This repository is not available to you through the GitHub App."
)
MSG_GITHUB_REPO_ALREADY_LINKED = _("This repository is already linked to the project.")
MSG_GITHUB_REF_NOT_FOUND = _("Branch or pull request not found in this repository.")
MSG_GITHUB_LINK_EXISTS = _("This branch or pull request is already linked to the task.")
MSG_GITHUB_SIGNATURE_INVALID = _("Invalid webhook signature.")
MSG_GITHUB_DISCONNECTED = _("GitHub account disconnected.")
MSG_GITHUB_UNLINK_NEEDS_PASSWORD = _(
    "Set a password (Forgot password) before unlinking your GitHub login."
)
