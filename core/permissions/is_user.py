from rest_framework.permissions import BasePermission


class IsUserOwner(BasePermission):
    """
    Allows access only to the user who manages themselves.
    """

    def has_object_permission(self, request, view, obj):
        return obj == request.user
