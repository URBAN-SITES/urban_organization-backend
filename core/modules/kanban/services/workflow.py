"""Saved views, custom fields, task templates and bulk edits of a project."""

from datetime import date
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import URLValidator
from django.db import transaction
from django.db.models import Q
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from core.models.user import User
from core.modules.kanban.models.custom_field import (
    CustomField,
    CustomFieldOption,
    TaskFieldValue,
)
from core.modules.kanban.models.saved_view import SavedView
from core.modules.kanban.models.task import Task
from core.modules.kanban.models.template import TaskTemplate
from core.modules.kanban.response_messages import (
    MSG_BULK_TASKS_INVALID,
    MSG_FIELD_NAME_TAKEN,
    MSG_FIELD_VALUE_INVALID,
    MSG_VIEW_NOT_YOURS,
)
from core.modules.kanban.services.label import LabelService
from core.modules.kanban.services.sector import Role, SectorService
from core.modules.kanban.services.task import TaskService


class SavedViewService:
    @staticmethod
    def list_for(user: User, sector_id):
        sector, _role = SectorService.get_sector(user, sector_id)
        return SavedView.objects.filter(
            Q(is_shared=True) | Q(owner=user), sector=sector
        ).order_by("position", "name")

    @staticmethod
    def create(user: User, sector_id, data: dict) -> SavedView:
        # anyone who sees the project may save a private view; sharing needs editor+
        minimum = Role.EDITOR if data.get("is_shared", True) else Role.VIEWER
        sector, _role = SectorService.get_sector(user, sector_id, minimum)
        return SavedView.objects.create(sector=sector, owner=user, **data)

    @staticmethod
    def update(user: User, view_id, data: dict) -> SavedView:
        view = SavedViewService._editable(user, view_id)
        if data.get("is_shared") and not view.is_shared:
            SectorService.get_sector(user, view.sector_id, Role.EDITOR)
        for field, value in data.items():
            setattr(view, field, value)
        view.save()
        return view

    @staticmethod
    def delete(user: User, view_id) -> None:
        SavedViewService._editable(user, view_id).delete()

    @staticmethod
    def _editable(user: User, view_id) -> SavedView:
        view = SavedView.objects.select_related("sector").filter(id=view_id).first()
        if view is None:
            raise NotFound()
        _sector, role = SectorService.get_sector(user, view.sector_id)
        if not view.is_shared and view.owner_id != user.pk:
            raise NotFound()
        if view.owner_id != user.pk and role != Role.MANAGER:
            raise PermissionDenied(MSG_VIEW_NOT_YOURS)
        return view


class CustomFieldService:
    @staticmethod
    def list_for(user: User, sector_id):
        sector, _role = SectorService.get_sector(user, sector_id)
        return CustomField.objects.filter(sector=sector).prefetch_related("options")

    @staticmethod
    @transaction.atomic
    def create(user: User, sector_id, data: dict) -> CustomField:
        sector, _role = SectorService.get_sector(user, sector_id, Role.MANAGER)
        options = data.pop("options", [])
        CustomFieldService._check_name(sector, data["name"])
        last = CustomField.objects.filter(sector=sector).count()
        field = CustomField.objects.create(sector=sector, position=last, **data)
        CustomFieldService._set_options(field, options)
        return field

    @staticmethod
    @transaction.atomic
    def update(user: User, field_id, data: dict) -> CustomField:
        field = CustomFieldService._get(user, field_id, Role.MANAGER)
        options = data.pop("options", None)
        data.pop("type", None)  # the type is fixed: values would not fit another
        if "name" in data:
            CustomFieldService._check_name(field.sector, data["name"], exclude=field.pk)
        for key, value in data.items():
            setattr(field, key, value)
        field.save()
        if options is not None:
            CustomFieldService._set_options(field, options)
        return field

    @staticmethod
    def delete(user: User, field_id) -> None:
        CustomFieldService._get(user, field_id, Role.MANAGER).delete()

    @staticmethod
    def values_for(user: User, task_id) -> list[dict]:
        task, _sector, _role = TaskService.get_task(user, task_id)
        return [
            {"field_id": row.field_id, "value": CustomFieldService.read(row)}
            for row in TaskFieldValue.objects.filter(task=task).select_related("field")
        ]

    @staticmethod
    def set_value(user: User, task_id, field_id, value) -> dict:
        task, sector, _role = TaskService.get_task(user, task_id, Role.EDITOR)
        field = CustomField.objects.filter(id=field_id, sector=sector).first()
        if field is None:
            raise NotFound()
        if value in (None, ""):
            TaskFieldValue.objects.filter(task=task, field=field).delete()
            return {"field_id": field.pk, "value": None}
        row, _created = TaskFieldValue.objects.get_or_create(task=task, field=field)
        CustomFieldService._write(row, field, value)
        row.save()
        return {"field_id": field.pk, "value": CustomFieldService.read(row)}

    @staticmethod
    def read(row: TaskFieldValue):
        kind = row.field.type
        if kind in (CustomField.Type.TEXT, CustomField.Type.URL):
            return row.value_text or None
        if kind == CustomField.Type.NUMBER:
            return None if row.value_number is None else float(row.value_number)
        if kind == CustomField.Type.DATE:
            return row.value_date.isoformat() if row.value_date else None
        if kind == CustomField.Type.CHECKBOX:
            return row.value_bool
        return str(row.option_id) if row.option_id else None

    @staticmethod
    def _write(row: TaskFieldValue, field: CustomField, value) -> None:
        kind = field.type
        try:
            if kind == CustomField.Type.TEXT:
                row.value_text = str(value)[:5000]
            elif kind == CustomField.Type.URL:
                URLValidator(schemes=["http", "https"])(str(value))
                row.value_text = str(value)[:2000]
            elif kind == CustomField.Type.NUMBER:
                row.value_number = Decimal(str(value))
                if not row.value_number.is_finite():
                    raise InvalidOperation
            elif kind == CustomField.Type.DATE:
                row.value_date = date.fromisoformat(str(value))
            elif kind == CustomField.Type.CHECKBOX:
                if not isinstance(value, bool):
                    raise TypeError
                row.value_bool = value
            else:
                option = field.options.filter(id=str(value)).first()
                if option is None:
                    raise ValueError
                row.option = option
        except ValueError, TypeError, InvalidOperation, DjangoValidationError:
            raise ValidationError({"value": [MSG_FIELD_VALUE_INVALID]}) from None

    @staticmethod
    def _set_options(field: CustomField, options: list[dict]) -> None:
        if field.type != CustomField.Type.SELECT:
            return
        keep = []
        for position, item in enumerate(options):
            option = (
                field.options.filter(id=item["id"]).first() if item.get("id") else None
            ) or CustomFieldOption(field=field)
            option.name, option.color, option.position = (
                item["name"],
                item.get("color", ""),
                position,
            )
            option.save()
            keep.append(option.pk)
        field.options.exclude(pk__in=keep).delete()

    @staticmethod
    def _get(user: User, field_id, minimum: str) -> CustomField:
        field = CustomField.objects.select_related("sector").filter(id=field_id).first()
        if field is None or not field.sector.is_active:
            raise NotFound()
        SectorService.get_sector(user, field.sector_id, minimum)
        return field

    @staticmethod
    def _check_name(sector, name: str, exclude=None) -> None:
        taken = CustomField.objects.filter(sector=sector, name__iexact=name)
        if exclude:
            taken = taken.exclude(pk=exclude)
        if taken.exists():
            raise ValidationError({"name": [MSG_FIELD_NAME_TAKEN]})


class TemplateService:
    @staticmethod
    def list_for(user: User, sector_id):
        sector, _role = SectorService.get_sector(user, sector_id)
        return TaskTemplate.objects.filter(sector=sector)

    @staticmethod
    def create(user: User, sector_id, data: dict) -> TaskTemplate:
        sector, _role = SectorService.get_sector(user, sector_id, Role.EDITOR)
        TemplateService._check_labels(sector, data)
        return TaskTemplate.objects.create(sector=sector, created_by=user, **data)

    @staticmethod
    def update(user: User, template_id, data: dict) -> TaskTemplate:
        template = TemplateService._get(user, template_id)
        TemplateService._check_labels(template.sector, data)
        for field, value in data.items():
            setattr(template, field, value)
        template.save()
        return template

    @staticmethod
    def delete(user: User, template_id) -> None:
        TemplateService._get(user, template_id).delete()

    @staticmethod
    def _check_labels(sector, data: dict) -> None:
        if data.get("label_ids"):
            data["label_ids"] = [
                str(label.pk)
                for label in LabelService.resolve(sector, data["label_ids"])
            ]

    @staticmethod
    def _get(user: User, template_id) -> TaskTemplate:
        template = (
            TaskTemplate.objects.select_related("sector").filter(id=template_id).first()
        )
        if template is None or not template.sector.is_active:
            raise NotFound()
        SectorService.get_sector(user, template.sector_id, Role.EDITOR)
        return template


class BulkService:
    UPDATE_KEYS = ("assignee", "cycle", "epic", "priority", "due_date", "estimate")

    @staticmethod
    @transaction.atomic
    def apply(user: User, sector_id, task_ids: list, changes: dict) -> int:
        """Same rules as one-by-one edits (move, update, archive, delete)."""
        sector, _role = SectorService.get_sector(user, sector_id, Role.EDITOR)
        tasks = list(
            Task.objects.filter(id__in=task_ids, sector=sector, is_active=True)
        )
        if not tasks or len(tasks) != len(set(task_ids)):
            raise ValidationError({"task_ids": [MSG_BULK_TASKS_INVALID]})
        if changes.get("delete"):
            for task in tasks:
                TaskService.delete(user, task.pk)
            return len(tasks)
        status = changes.get("status")
        label = changes.get("add_label")
        if label is not None and label.sector_id != sector.pk:
            raise ValidationError({"add_label": [MSG_BULK_TASKS_INVALID]})
        update = {k: changes[k] for k in BulkService.UPDATE_KEYS if k in changes}
        for task in tasks:
            if status is not None and status.pk != task.status_id:
                TaskService.move(user, task.pk, status, None)
            if update:
                TaskService.update(user, task.pk, dict(update))
            if label is not None and not task.labels.filter(pk=label.pk).exists():
                TaskService._set_labels(task, user, [*task.labels.all(), label])
            if "archive" in changes:
                TaskService.set_archived(user, task.pk, changes["archive"])
        return len(tasks)
