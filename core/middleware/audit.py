from auditlog.middleware import AuditlogMiddleware as BaseAuditlogMiddleware
from django.utils.functional import SimpleLazyObject


class AuditlogMiddleware(BaseAuditlogMiddleware):
    """DRF authenticates the JWT inside the view, so resolve the actor lazily."""

    def get_extra_data(self, request):
        context_data = super().get_extra_data(request)
        context_data["actor"] = SimpleLazyObject(lambda: self._get_actor(request))
        return context_data
