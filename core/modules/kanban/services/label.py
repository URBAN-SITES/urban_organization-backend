from rest_framework.exceptions import NotFound, ValidationError

from core.models.user import User
from core.modules.kanban.models.label import Label
from core.modules.kanban.models.sector import Sector
from core.modules.kanban.response_messages import (
    MSG_LABEL_INVALID,
    MSG_LABEL_NAME_TAKEN,
)
from core.modules.kanban.services.sector import Role, SectorService


class LabelService:
    @staticmethod
    def list_for(user: User, sector_id):
        sector, _role = SectorService.get_sector(user, sector_id)
        return Label.objects.filter(sector=sector)

    @staticmethod
    def create(user: User, sector_id, name: str, color: str = "") -> Label:
        sector, _role = SectorService.get_sector(user, sector_id, Role.EDITOR)
        LabelService._check_name(sector, name)
        return Label.objects.create(sector=sector, name=name, color=color)

    @staticmethod
    def update(user: User, label_id, data: dict) -> Label:
        label = LabelService._get(user, label_id, Role.EDITOR)
        if "name" in data:
            LabelService._check_name(label.sector, data["name"], exclude=label.pk)
        for field, value in data.items():
            setattr(label, field, value)
        label.save()
        return label

    @staticmethod
    def delete(user: User, label_id) -> None:
        LabelService._get(user, label_id, Role.EDITOR).delete()

    @staticmethod
    def resolve(sector: Sector, ids) -> list[Label]:
        """The sector's labels with these ids; any foreign or unknown id is a 400."""
        wanted = set(ids)
        labels = list(Label.objects.filter(sector=sector, id__in=wanted))
        if len(labels) != len(wanted):
            raise ValidationError({"label_ids": [MSG_LABEL_INVALID]})
        return labels

    @staticmethod
    def _get(user: User, label_id, minimum: str) -> Label:
        label = (
            Label.objects.select_related("sector")
            .filter(id=label_id, sector__is_active=True)
            .first()
        )
        if label is None:
            raise NotFound()
        SectorService.get_sector(user, label.sector_id, minimum)
        return label

    @staticmethod
    def _check_name(sector: Sector, name: str, exclude=None) -> None:
        taken = Label.objects.filter(sector=sector, name__iexact=name)
        if exclude:
            taken = taken.exclude(pk=exclude)
        if taken.exists():
            raise ValidationError({"name": [MSG_LABEL_NAME_TAKEN]})
