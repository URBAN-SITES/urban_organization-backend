from django.contrib import admin

from core.modules.chat.models.chat import ChatChannel, ChatMessage


@admin.register(ChatChannel)
class ChatChannelAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "organization", "team", "created_at")
    list_filter = ("kind", "created_at")
    search_fields = ("name", "organization__name")


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ("author", "channel", "created_at", "deleted_at")
    list_filter = ("created_at",)
    search_fields = ("content", "author__email")
