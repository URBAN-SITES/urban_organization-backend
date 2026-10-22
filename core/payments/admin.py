from django.contrib import admin

from core.payments.models.payment import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "amount", "status", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("title", "user__email", "provider_payment_id")
    readonly_fields = [field.name for field in Payment._meta.fields]
