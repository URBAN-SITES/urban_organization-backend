from core.models.user import User
from core.modules.kanban.models.follow import TaskSubscriber
from core.modules.kanban.services.task import TaskService


class FollowService:
    @staticmethod
    def state(user: User, task_id) -> dict:
        task, _sector, _role = TaskService.get_task(user, task_id)
        return FollowService._state(user, task)

    @staticmethod
    def set(user: User, task_id, following: bool) -> dict:
        # viewers may follow too: following only reads
        task, _sector, _role = TaskService.get_task(user, task_id)
        if following:
            TaskSubscriber.objects.get_or_create(task=task, user=user)
        else:
            TaskSubscriber.objects.filter(task=task, user=user).delete()
        return FollowService._state(user, task)

    @staticmethod
    def _state(user: User, task) -> dict:
        followers = TaskSubscriber.objects.filter(task=task)
        return {
            "following": followers.filter(user=user).exists(),
            "followers": followers.count(),
        }
