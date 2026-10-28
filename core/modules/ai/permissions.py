import os

from rest_framework.permissions import BasePermission


def has_temporary_access(user) -> bool:
    """E-mails in AI_TEMPORARY_ACCESS_EMAILS use the assistant without paying."""
    allowed = {
        email.strip().lower()
        for email in os.getenv("AI_TEMPORARY_ACCESS_EMAILS", "").split(",")
        if email.strip()
    }
    return bool(user.is_authenticated and user.email.lower() in allowed)


class IsSubscriber(BasePermission):
    message = "Confirme um pagamento para liberar o acesso à IA."
    code = "subscription_required"

    def has_permission(self, request, view):
        return bool(request.user.is_authenticated and request.user.is_subscriber)


class HasAssistantAccess(IsSubscriber):
    """Subscribers, plus the temporary list; file analysis stays subscriber-only."""

    def has_permission(self, request, view):
        return super().has_permission(request, view) or has_temporary_access(
            request.user
        )
