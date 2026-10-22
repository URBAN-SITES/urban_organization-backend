from django.urls import path

from core.modules.payments.views.payment import (
    PaymentListCreateView,
    PaymentWebhookView,
)

app_name = "payments"

urlpatterns = [
    path("", PaymentListCreateView.as_view(), name="list-create"),
    path("webhook/", PaymentWebhookView.as_view(), name="webhook"),
]
