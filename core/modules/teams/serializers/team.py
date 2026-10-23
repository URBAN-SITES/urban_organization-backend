from rest_framework import serializers

from core.modules.teams.models.team import Team, TeamMember


class TeamSerializer(serializers.ModelSerializer):
    class Meta:
        model = Team
        fields = ("id", "name", "description", "created_at")
        read_only_fields = ("id", "created_at")


class TeamMemberSerializer(serializers.ModelSerializer):
    user_id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(source="user.name", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = TeamMember
        fields = ("id", "user_id", "name", "email", "role", "joined_at")
        read_only_fields = fields


class TeamMemberAddSerializer(serializers.Serializer):
    user_id = serializers.UUIDField()
    role = serializers.ChoiceField(
        choices=TeamMember.Role, default=TeamMember.Role.MEMBER
    )


class TeamMemberRoleSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=TeamMember.Role)
