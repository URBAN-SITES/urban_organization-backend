from django.contrib import admin

from core.modules.crowdfunding.models.campaign import Campaign, Contribution


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ("title", "organization", "goal_amount", "status", "deadline")
    list_filter = ("status",)
    search_fields = ("title", "organization__name")


@admin.register(Contribution)
class ContributionAdmin(admin.ModelAdmin):
    list_display = ("campaign", "user", "payment", "anonymous", "created_at")
    readonly_fields = [field.name for field in Contribution._meta.fields]
