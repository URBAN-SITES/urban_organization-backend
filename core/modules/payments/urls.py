from django.urls import path

from core.modules.payments.views.payment import (
    PaymentCardCreateView,
    PaymentPixListCreateView,
    PaymentWebhookView,
)

app_name = "payments"

urlpatterns = [
    path("", PaymentPixListCreateView.as_view(), name="list-create"),
    path("card/", PaymentCardCreateView.as_view(), name="card-create"),
    path("webhook/", PaymentWebhookView.as_view(), name="webhook"),
]
