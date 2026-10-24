from django.urls import path

from core.modules.kanban.views import item, sector, task

app_name = "kanban"

# mounted at the API root: sectors/tasks are addressed by their own (global) UUID
urlpatterns = [
    path(
        "organizations/<uuid:organization_id>/sectors/",
        sector.SectorListCreateView.as_view(),
        name="sector-list",
    ),
    path(
        "organizations/<uuid:organization_id>/dashboard/",
        sector.DashboardView.as_view(),
        name="dashboard",
    ),
    path(
        "organizations/<uuid:organization_id>/calendar/",
        sector.CalendarView.as_view(),
        name="calendar",
    ),
    path(
        "organizations/<uuid:organization_id>/reports/",
        sector.ReportView.as_view(),
        name="reports",
    ),
    path(
        "organizations/<uuid:organization_id>/files/",
        sector.FileListView.as_view(),
        name="files",
    ),
    path(
        "organizations/<uuid:organization_id>/links/",
        item.OrganizationLinkListCreateView.as_view(),
        name="organization-link-list",
    ),
    path(
        "sectors/<uuid:sector_id>/",
        sector.SectorDetailView.as_view(),
        name="sector-detail",
    ),
    path(
        "sectors/<uuid:sector_id>/progress/",
        sector.SectorProgressView.as_view(),
        name="sector-progress",
    ),
    path(
        "sectors/<uuid:sector_id>/members/",
        sector.SectorMemberListCreateView.as_view(),
        name="sector-member-list",
    ),
    path(
        "sectors/<uuid:sector_id>/members/<int:member_id>/",
        sector.SectorMemberDetailView.as_view(),
        name="sector-member-detail",
    ),
    path(
        "sectors/<uuid:sector_id>/teams/",
        sector.SectorTeamListCreateView.as_view(),
        name="sector-team-list",
    ),
    path(
        "sectors/<uuid:sector_id>/teams/<int:link_id>/",
        sector.SectorTeamDetailView.as_view(),
        name="sector-team-detail",
    ),
    path(
        "sectors/<uuid:sector_id>/statuses/",
        sector.StatusListCreateView.as_view(),
        name="status-list",
    ),
    path(
        "sectors/<uuid:sector_id>/statuses/<uuid:status_id>/",
        sector.StatusDetailView.as_view(),
        name="status-detail",
    ),
    path(
        "sectors/<uuid:sector_id>/tasks/",
        task.TaskListCreateView.as_view(),
        name="task-list",
    ),
    path(
        "sectors/<uuid:sector_id>/links/",
        item.SectorLinkListCreateView.as_view(),
        name="sector-link-list",
    ),
    path("tasks/<uuid:task_id>/", task.TaskDetailView.as_view(), name="task-detail"),
    path("tasks/<uuid:task_id>/move/", task.TaskMoveView.as_view(), name="task-move"),
    path(
        "tasks/<uuid:task_id>/checklist/",
        item.ChecklistListCreateView.as_view(),
        name="checklist-list",
    ),
    path(
        "tasks/<uuid:task_id>/checklist/<uuid:item_id>/",
        item.ChecklistDetailView.as_view(),
        name="checklist-detail",
    ),
    path(
        "tasks/<uuid:task_id>/comments/",
        item.CommentListCreateView.as_view(),
        name="comment-list",
    ),
    path(
        "tasks/<uuid:task_id>/comments/<uuid:comment_id>/",
        item.CommentDetailView.as_view(),
        name="comment-detail",
    ),
    path(
        "tasks/<uuid:task_id>/links/",
        item.TaskLinkListCreateView.as_view(),
        name="task-link-list",
    ),
    path("links/<uuid:link_id>/", item.LinkDetailView.as_view(), name="link-detail"),
]
