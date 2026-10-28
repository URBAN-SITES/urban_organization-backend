from rest_framework import serializers

from core.modules.kanban.models.sector import Sector, SectorMember
from core.modules.kanban.models.task import Status
from core.modules.teams.models.team import SectorTeam


class SectorSerializer(serializers.ModelSerializer):
    organization_id = serializers.UUIDField(read_only=True)
    # explicit default: multipart forms would otherwise turn a missing flag into False
    is_private = serializers.BooleanField(default=True)
    # annotated by the list/detail views; absent on plain instances
    is_favorite = serializers.SerializerMethodField()
    task_total = serializers.SerializerMethodField()
    task_done = serializers.SerializerMethodField()

    class Meta:
        model = Sector
        fields = (
            "id",
            "organization_id",
            "name",
            "description",
            "icon",
            "color",
            "is_private",
            "archived_at",
            "is_favorite",
            "task_total",
            "task_done",
            "created_at",
        )
        read_only_fields = ("id", "organization_id", "archived_at", "created_at")

    def get_is_favorite(self, obj) -> bool:
        return bool(getattr(obj, "is_favorite", False))

    def get_task_total(self, obj) -> int | None:
        return getattr(obj, "task_total", None)

    def get_task_done(self, obj) -> int | None:
        return getattr(obj, "task_done", None)


class SectorMemberSerializer(serializers.ModelSerializer):
    user_id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(source="user.name", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = SectorMember
        fields = ("id", "user_id", "name", "email", "role")
        read_only_fields = fields


class SectorMemberAddSerializer(serializers.Serializer):
    user_id = serializers.UUIDField()
    role = serializers.ChoiceField(
        choices=SectorMember.Role, default=SectorMember.Role.EDITOR
    )


class SectorMemberRoleSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=SectorMember.Role)


class SectorTeamSerializer(serializers.ModelSerializer):
    team_id = serializers.UUIDField(read_only=True)
    team_name = serializers.CharField(source="team.name", read_only=True)

    class Meta:
        model = SectorTeam
        fields = ("id", "team_id", "team_name", "role")
        read_only_fields = fields


class SectorTeamAddSerializer(serializers.Serializer):
    team_id = serializers.UUIDField()
    role = serializers.ChoiceField(
        choices=SectorMember.Role, default=SectorMember.Role.EDITOR
    )


class SectorProgressSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    completed = serializers.IntegerField()
    overdue = serializers.IntegerField()
    percent = serializers.FloatField()


class StatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = Status
        fields = ("id", "name", "color", "category", "position", "wip_limit")
        read_only_fields = ("id",)
        extra_kwargs = {"position": {"required": False}}
