from django.middleware import csrf
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.modules.github.models.github import GitHubConnection, GitHubIdentity
from core.modules.github.response_messages import MSG_GITHUB_DISCONNECTED
from core.modules.github.serializers.github import (
    AuthorizeQuerySerializer,
    AuthorizeSerializer,
    CallbackResultSerializer,
    CallbackSerializer,
    GitHubStatusSerializer,
    LinkRepositoriesSerializer,
    ProjectRepositorySerializer,
    RefOptionSerializer,
    RefSearchQuerySerializer,
    RepositoryPageSerializer,
    RepositoryQuerySerializer,
    TaskLinkSerializer,
    TaskLinkWriteSerializer,
)
from core.modules.github.services.client import GitHubNotConfigured, app_settings
from core.modules.github.services.oauth import (
    CONNECT,
    LINK,
    LOGIN,
    GitHubOAuthService,
)
from core.modules.github.services.repos import GitHubRepoService
from core.modules.github.services.webhook import GitHubWebhookService
from core.response_messages import MSG_LOGIN_SUCCESSFUL
from core.utils.cookies import set_auth_cookies


def _user(request):
    return request.user if request.user and request.user.is_authenticated else None


@extend_schema(tags=["Integrações"])
class GitHubStatusView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="My GitHub login and connection",
        responses={200: GitHubStatusSerializer},
    )
    def get(self, request):
        try:
            app_settings()
            configured = True
        except GitHubNotConfigured:
            configured = False
        identity = GitHubIdentity.objects.filter(user=request.user).first()
        connection = GitHubConnection.objects.filter(user=request.user).first()
        return Response(
            {
                "configured": configured,
                "install_url": GitHubRepoService.install_url() if configured else "",
                "identity": {"login": identity.login} if identity else None,
                "connection": (
                    {
                        "login": connection.login,
                        "avatar_url": connection.avatar_url,
                        "connected_at": connection.created_at,
                    }
                    if connection
                    else None
                ),
                "can_unlink": request.user.has_usable_password(),
            }
        )


@extend_schema(tags=["Integrações"])
class GitHubAuthorizeView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        summary="GitHub consent URL: purpose=login (anonymous), link or connect",
        parameters=[AuthorizeQuerySerializer],
        responses={200: AuthorizeSerializer},
    )
    def get(self, request):
        query = AuthorizeQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        url = GitHubOAuthService.authorize_url(
            query.validated_data["purpose"], _user(request)
        )
        return Response({"url": url})


@extend_schema(tags=["Integrações"])
class GitHubCallbackView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "auth"

    @extend_schema(
        summary="Finish a GitHub authorization with the code and state GitHub sent back",
        description="login sets the same JWT cookies as the e-mail login; link and connect need a session.",
        request=CallbackSerializer,
        responses={200: CallbackResultSerializer},
    )
    def post(self, request):
        serializer = CallbackSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        code, state = (
            serializer.validated_data["code"],
            serializer.validated_data["state"],
        )
        purpose = GitHubOAuthService.read_state(state, _user(request))
        if purpose == LOGIN:
            tokens = GitHubOAuthService.login(
                code,
                request.META.get("HTTP_USER_AGENT", ""),
                request.META.get("REMOTE_ADDR"),
            )
            response = Response(
                {"purpose": LOGIN, "detail": MSG_LOGIN_SUCCESSFUL}, status.HTTP_200_OK
            )
            set_auth_cookies(response, tokens)
            csrf.get_token(request)
            return response
        if purpose == LINK:
            identity = GitHubOAuthService.link(request.user, code)
            return Response({"purpose": LINK, "login": identity.login})
        connection = GitHubOAuthService.connect(request.user, code)
        return Response({"purpose": CONNECT, "login": connection.login})


@extend_schema(tags=["Integrações"])
class GitHubConnectionView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Revoke the GitHub authorization and delete its tokens",
        responses={200: None},
    )
    def delete(self, request):
        revoked = GitHubOAuthService.disconnect(request.user)
        return Response({"detail": MSG_GITHUB_DISCONNECTED, "revoked": revoked})


@extend_schema(tags=["Integrações"])
class GitHubIdentityView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Stop logging in with GitHub", responses={204: None})
    def delete(self, request):
        GitHubOAuthService.unlink(request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=["Integrações"])
class GitHubRepositoriesView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Repositories I reach through the GitHub App (search, filters, pages of 20)",
        parameters=[RepositoryQuerySerializer],
        responses={200: RepositoryPageSerializer},
    )
    def get(self, request):
        query = RepositoryQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        return Response(GitHubRepoService.search(request.user, query.validated_data))


@extend_schema(tags=["Integrações"])
class ProjectRepositoriesView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Repositories linked to the project",
        responses={200: ProjectRepositorySerializer(many=True)},
    )
    def get(self, request, sector_id):
        rows = GitHubRepoService.list_for_project(request.user, sector_id)
        return Response(ProjectRepositorySerializer(rows, many=True).data)

    @extend_schema(
        summary="Link repositories to the project (manager)",
        request=LinkRepositoriesSerializer,
        responses={201: ProjectRepositorySerializer(many=True)},
    )
    def post(self, request, sector_id):
        serializer = LinkRepositoriesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        rows = GitHubRepoService.link(
            request.user, sector_id, serializer.validated_data["github_ids"]
        )
        return Response(
            ProjectRepositorySerializer(rows, many=True).data,
            status=status.HTTP_201_CREATED,
        )


@extend_schema(tags=["Integrações"])
class ProjectRepositoryDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Unlink a repository from the project (GitHub is not touched)",
        responses={204: None},
    )
    def delete(self, request, sector_id, repository_id):
        GitHubRepoService.unlink(request.user, sector_id, repository_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=["Integrações"])
class RepositoryActivityView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Recent branches, pull requests (with checks) and issues",
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request, repository_id):
        return Response(GitHubRepoService.activity(request.user, repository_id))


@extend_schema(tags=["Integrações"])
class TaskGitHubLinksView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Branches and pull requests linked to the task",
        responses={200: TaskLinkSerializer(many=True)},
    )
    def get(self, request, task_id):
        rows = GitHubRepoService.task_links(request.user, task_id)
        return Response(TaskLinkSerializer(rows, many=True).data)

    @extend_schema(
        summary="Link a branch or pull request to the task (editor)",
        request=TaskLinkWriteSerializer,
        responses={201: TaskLinkSerializer},
    )
    def post(self, request, task_id):
        serializer = TaskLinkWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        link = GitHubRepoService.link_task(
            request.user, task_id, **serializer.validated_data
        )
        return Response(TaskLinkSerializer(link).data, status=status.HTTP_201_CREATED)


@extend_schema(tags=["Integrações"])
class TaskGitHubLinkDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Unlink a branch or pull request", responses={204: None})
    def delete(self, request, task_id, link_id):
        GitHubRepoService.unlink_task(request.user, task_id, link_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=["Integrações"])
class TaskGitHubSearchView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Find branches and pull requests of the project's repositories",
        parameters=[RefSearchQuerySerializer],
        responses={200: RefOptionSerializer(many=True)},
    )
    def get(self, request, task_id):
        query = RefSearchQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        return Response(
            GitHubRepoService.search_refs(
                request.user, task_id, query.validated_data["q"]
            )
        )


@extend_schema(tags=["Integrações"])
class GitHubWebhookView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        summary="GitHub App webhook (HMAC-SHA256 signed)",
        request=None,
        responses={204: None},
    )
    def post(self, request):
        body = request.body  # the signature covers the raw bytes
        GitHubWebhookService.verify(
            body, request.headers.get("X-Hub-Signature-256", "")
        )
        GitHubWebhookService.handle(
            request.headers.get("X-GitHub-Event", ""), request.data
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
