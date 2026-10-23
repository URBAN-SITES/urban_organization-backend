from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.modules.kanban.serializers.task import (
    ChecklistItemSerializer,
    CommentSerializer,
    CommentWriteSerializer,
    ResourceLinkSerializer,
)
from core.modules.kanban.services.item import (
    ChecklistService,
    CommentService,
    LinkService,
)


class ChecklistListCreateView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ChecklistItemSerializer

    @extend_schema(summary="List a task's checklist")
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        return ChecklistService.list_for(self.request.user, self.kwargs["task_id"])

    @extend_schema(
        summary="Add a checklist item (editor+)",
        request=ChecklistItemSerializer,
        responses={201: ChecklistItemSerializer},
    )
    def post(self, request, task_id):
        serializer = ChecklistItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = ChecklistService.create(
            request.user, task_id, dict(serializer.validated_data)
        )
        return Response(
            ChecklistItemSerializer(item).data, status=status.HTTP_201_CREATED
        )


class ChecklistDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Edit/check a checklist item (editor+)",
        request=ChecklistItemSerializer,
        responses={200: ChecklistItemSerializer},
    )
    def patch(self, request, task_id, item_id):
        serializer = ChecklistItemSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        item = ChecklistService.update(
            request.user, task_id, item_id, serializer.validated_data
        )
        return Response(ChecklistItemSerializer(item).data)

    @extend_schema(summary="Delete a checklist item (editor+)", responses={204: None})
    def delete(self, request, task_id, item_id):
        ChecklistService.delete(request.user, task_id, item_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


class CommentListCreateView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = CommentSerializer

    @extend_schema(summary="List a task's comments")
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        return CommentService.list_for(self.request.user, self.kwargs["task_id"])

    @extend_schema(
        summary="Comment on a task (editor+); notifies the assignee",
        request=CommentWriteSerializer,
        responses={201: CommentSerializer},
    )
    def post(self, request, task_id):
        serializer = CommentWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        comment = CommentService.create(
            request.user, task_id, serializer.validated_data["content"]
        )
        return Response(CommentSerializer(comment).data, status=status.HTTP_201_CREATED)


class CommentDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Edit my comment",
        request=CommentWriteSerializer,
        responses={200: CommentSerializer},
    )
    def patch(self, request, task_id, comment_id):
        serializer = CommentWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        comment = CommentService.update(
            request.user, task_id, comment_id, serializer.validated_data["content"]
        )
        return Response(CommentSerializer(comment).data)

    @extend_schema(
        summary="Delete my comment (or any, as sector manager)", responses={204: None}
    )
    def delete(self, request, task_id, comment_id):
        CommentService.delete(request.user, task_id, comment_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


def _link_views(target: str, label: str):
    """Builds the list/create view of links for task, sector or organization."""
    lister = getattr(LinkService, f"list_for_{target}")
    creator = getattr(LinkService, f"create_for_{target}")
    key = f"{target}_id"

    class LinkListCreateView(ListAPIView):
        permission_classes = [IsAuthenticated]
        serializer_class = ResourceLinkSerializer

        @extend_schema(summary=f"List the links of a {label}")
        def get(self, request, *args, **kwargs):
            return super().get(request, *args, **kwargs)

        def get_queryset(self):
            return lister(self.request.user, self.kwargs[key])

        @extend_schema(
            summary=f"Add a supporting link to a {label}",
            request=ResourceLinkSerializer,
            responses={201: ResourceLinkSerializer},
        )
        def post(self, request, **kwargs):
            serializer = ResourceLinkSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            link = creator(request.user, kwargs[key], dict(serializer.validated_data))
            return Response(
                ResourceLinkSerializer(link).data, status=status.HTTP_201_CREATED
            )

    LinkListCreateView.__name__ = f"{target.capitalize()}LinkListCreateView"
    return LinkListCreateView


TaskLinkListCreateView = _link_views("task", "task")
SectorLinkListCreateView = _link_views("sector", "sector")
OrganizationLinkListCreateView = _link_views("organization", "organization")


class LinkDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Delete a link (creator, or manager/admin of its target)",
        responses={204: None},
    )
    def delete(self, request, link_id):
        LinkService.delete(request.user, link_id)
        return Response(status=status.HTTP_204_NO_CONTENT)
