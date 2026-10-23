from rest_framework import serializers

from core.modules.chat.models.chat import ChatChannel, ChatMessage
from core.modules.uploads.models.attachment import Attachment


class ChatChannelSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    kind = serializers.ChoiceField(choices=ChatChannel.Kind)
    name = serializers.CharField()
    team_id = serializers.UUIDField(allow_null=True)
    team_ids = serializers.ListField(child=serializers.UUIDField())
    sector_id = serializers.UUIDField(allow_null=True)
    unread_count = serializers.IntegerField()
    member_count = serializers.IntegerField()
    online = serializers.BooleanField(
        allow_null=True, help_text="Direct channels only: is the other person online?"
    )
    last_message = serializers.DictField(allow_null=True)


class ChatDirectOpenSerializer(serializers.Serializer):
    user_id = serializers.UUIDField()


class ChatTeamsChannelSerializer(serializers.Serializer):
    team_ids = serializers.ListField(
        child=serializers.UUIDField(), min_length=2, max_length=20
    )
    name = serializers.CharField(max_length=255, required=False, default="")


class ChatAttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Attachment
        fields = ("id", "file_name", "mime_type", "size_bytes", "url")
        read_only_fields = fields


class ChatMessageSerializer(serializers.ModelSerializer):
    channel_id = serializers.UUIDField(read_only=True)
    author_id = serializers.UUIDField(read_only=True)
    author_name = serializers.CharField(source="author.name", read_only=True)
    reply_to_id = serializers.UUIDField(read_only=True)
    task = serializers.SerializerMethodField()
    mentions = serializers.SerializerMethodField()
    attachments = ChatAttachmentSerializer(many=True, read_only=True)

    class Meta:
        model = ChatMessage
        fields = (
            "id",
            "channel_id",
            "author_id",
            "author_name",
            "content",
            "reply_to_id",
            "task",
            "mentions",
            "attachments",
            "created_at",
            "edited_at",
            "deleted_at",
        )
        read_only_fields = fields

    def get_task(self, message) -> dict | None:
        task = message.task
        if task is None or message.deleted_at:
            return None
        return {
            "id": str(task.id),
            "title": task.title,
            "sector_id": str(task.sector_id),
            "status": task.status.name,
            "completed": task.completed_at is not None,
        }

    def get_mentions(self, message) -> list[dict]:
        return [
            {"id": str(user.id), "name": user.name} for user in message.mentions.all()
        ]


class ChatMessageWriteSerializer(serializers.Serializer):
    content = serializers.CharField(max_length=4000, required=False, allow_blank=True)
    reply_to = serializers.UUIDField(required=False, allow_null=True)
    task = serializers.UUIDField(
        required=False, allow_null=True, help_text="Cite a task (the # in the composer)"
    )
    mentions = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        max_length=20,
        help_text="User ids mentioned with @",
    )
    files = serializers.ListField(
        child=serializers.FileField(), required=False, max_length=5
    )


class ChatMessageEditSerializer(serializers.Serializer):
    content = serializers.CharField(max_length=4000)
