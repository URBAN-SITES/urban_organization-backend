from rest_framework import serializers

from core.modules.github.models.github import ProjectRepository, TaskGitHubLink
from core.modules.github.services.oauth import PURPOSES


class AuthorizeQuerySerializer(serializers.Serializer):
    purpose = serializers.ChoiceField(choices=PURPOSES)


class AuthorizeSerializer(serializers.Serializer):
    url = serializers.URLField()


class CallbackSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=200)
    state = serializers.CharField(max_length=500)


class CallbackResultSerializer(serializers.Serializer):
    purpose = serializers.CharField()
    login = serializers.CharField(required=False)


class GitHubStatusSerializer(serializers.Serializer):
    configured = serializers.BooleanField()
    install_url = serializers.CharField(allow_blank=True)
    identity = serializers.DictField(allow_null=True)
    connection = serializers.DictField(allow_null=True)
    can_unlink = serializers.BooleanField()


class RepositoryQuerySerializer(serializers.Serializer):
    search = serializers.CharField(required=False, allow_blank=True, max_length=100)
    visibility = serializers.ChoiceField(
        choices=("all", "public", "private"), required=False, default="all"
    )
    language = serializers.CharField(required=False, allow_blank=True, max_length=60)
    page = serializers.IntegerField(
        required=False, default=1, min_value=1, max_value=500
    )
    refresh = serializers.BooleanField(required=False, default=False)


class AuthorizedRepositorySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    full_name = serializers.CharField()
    owner = serializers.CharField()
    private = serializers.BooleanField()
    language = serializers.CharField(allow_blank=True)
    description = serializers.CharField(allow_blank=True)
    html_url = serializers.URLField()
    default_branch = serializers.CharField(allow_blank=True)
    pushed_at = serializers.CharField(allow_null=True)
    installation_id = serializers.IntegerField()


class RepositoryPageSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    results = AuthorizedRepositorySerializer(many=True)
    languages = serializers.ListField(child=serializers.CharField())


class ProjectRepositorySerializer(serializers.ModelSerializer):
    linked_by_name = serializers.CharField(
        source="linked_by.name", read_only=True, default=""
    )

    class Meta:
        model = ProjectRepository
        fields = (
            "id",
            "github_id",
            "full_name",
            "private",
            "html_url",
            "default_branch",
            "language",
            "linked_by_name",
            "created_at",
        )
        read_only_fields = fields


class LinkRepositoriesSerializer(serializers.Serializer):
    github_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1), min_length=1, max_length=20
    )


class TaskLinkSerializer(serializers.ModelSerializer):
    repository_id = serializers.UUIDField(read_only=True)
    repository = serializers.CharField(source="repository.full_name", read_only=True)

    class Meta:
        model = TaskGitHubLink
        fields = (
            "id",
            "repository_id",
            "repository",
            "kind",
            "ref",
            "title",
            "state",
            "html_url",
            "created_at",
        )
        read_only_fields = fields


class TaskLinkWriteSerializer(serializers.Serializer):
    repository_id = serializers.UUIDField()
    kind = serializers.ChoiceField(choices=TaskGitHubLink.Kind.choices)
    ref = serializers.CharField(max_length=255)


class RefSearchQuerySerializer(serializers.Serializer):
    q = serializers.CharField(
        required=False, allow_blank=True, max_length=100, default=""
    )


class RefOptionSerializer(serializers.Serializer):
    repository_id = serializers.UUIDField()
    repository = serializers.CharField()
    kind = serializers.CharField()
    ref = serializers.CharField()
    title = serializers.CharField()
    state = serializers.CharField(allow_blank=True)
