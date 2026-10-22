from rest_framework.permissions import BasePermission

from core.response_messages import MSG_ROLE_REQUIRED


class HasRole(BasePermission):
    """
    Roles are Django Groups (managed in the admin).

    Usage on a view:
        permission_classes = [IsAuthenticated, HasRole]
        required_roles = ["admin", "manager"]  # any of them grants access

    Superusers always pass. For per-model add/change/delete rules use
    DRF's built-in DjangoModelPermissions instead.
    """

    message = MSG_ROLE_REQUIRED

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        required_roles = getattr(view, "required_roles", [])
        return user.groups.filter(name__in=required_roles).exists()
