from django.urls import path

from core.modules.payments.views.payment import PaymentWebhookView

app_name = "payments"

# só o retorno do Mercado Pago, usado pelas cobranças das tarefas (crowdfunding)
urlpatterns = [
    path("webhook/", PaymentWebhookView.as_view(), name="webhook"),
]
