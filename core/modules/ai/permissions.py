from rest_framework.permissions import BasePermission


class IsSubscriber(BasePermission):
    message = "Confirme um pagamento para liberar o acesso à IA."
    code = "subscription_required"

    def has_permission(self, request, view):
        return bool(request.user.is_authenticated and request.user.is_subscriber)
