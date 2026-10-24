from decimal import Decimal

from django.db import transaction
from django.db.models import Count, DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from core.models.user import User
from core.modules.crowdfunding.models.campaign import Campaign, Contribution
from core.modules.crowdfunding.response_messages import (
    MSG_CAMPAIGN_CLOSED,
    MSG_CAMPAIGN_EXPIRED,
    MSG_CAMPAIGN_NOT_FOUND,
)
from core.modules.kanban.services.sector import Role as SectorRole
from core.modules.kanban.services.task import TaskService
from core.modules.organizations.models.organization import OrganizationMember
from core.modules.organizations.services.organization import OrganizationService
from core.modules.payments.models.payment import Payment
from core.modules.payments.services.payment import PaymentService

Role = OrganizationMember.Role
APPROVED = Q(contributions__payment__status=Payment.Status.APPROVED)


def _with_totals(queryset):
    """`raised` and `contributors` count approved payments only."""
    return queryset.annotate(
        raised=Coalesce(
            Sum("contributions__payment__amount", filter=APPROVED),
            Value(Decimal("0.00")),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        ),
        contributors=Count("contributions", filter=APPROVED),
    )


class CampaignService:
    @staticmethod
    def list_for(user: User, organization_id):
        OrganizationService.get_membership(user, organization_id)
        # task charges are listed on their task, not here
        return _with_totals(
            Campaign.objects.filter(organization_id=organization_id, task=None)
        ).order_by("-created_at")

    @staticmethod
    def list_for_task(user: User, task_id):
        task, _sector, _role = TaskService.get_task(user, task_id)
        return _with_totals(Campaign.objects.filter(task=task)).order_by("created_at")

    @staticmethod
    def create_for_task(user: User, task_id, data: dict) -> Campaign:
        task, sector, _role = TaskService.get_task(user, task_id, SectorRole.EDITOR)
        campaign = Campaign.objects.create(
            organization_id=sector.organization_id, task=task, created_by=user, **data
        )
        return CampaignService.get(user, campaign.id)

    @staticmethod
    def create(user: User, organization_id, data: dict) -> Campaign:
        OrganizationService.require_role(user, organization_id, Role.ADMIN)
        campaign = Campaign.objects.create(
            organization_id=organization_id, created_by=user, **data
        )
        return CampaignService.get(user, campaign.id)

    @staticmethod
    def get(user: User, campaign_id) -> Campaign:
        """The campaign with its totals; 404 for non-members of its organization."""
        campaign = _with_totals(Campaign.objects.filter(id=campaign_id)).first()
        if campaign is None:
            raise NotFound(MSG_CAMPAIGN_NOT_FOUND)
        if campaign.task_id:  # a task charge follows the access to its task
            TaskService.get_task(user, campaign.task_id)
        else:
            OrganizationService.get_membership(user, campaign.organization_id)
        return campaign

    @staticmethod
    def update(user: User, campaign_id, data: dict) -> Campaign:
        campaign = CampaignService.get(user, campaign_id)
        if campaign.task_id:
            TaskService.get_task(user, campaign.task_id, SectorRole.EDITOR)
        else:
            OrganizationService.require_role(user, campaign.organization_id, Role.ADMIN)
        for field, value in data.items():
            setattr(campaign, field, value)
        campaign.save(update_fields=[*data, "updated_at"])
        return CampaignService.get(user, campaign_id)

    @staticmethod
    def list_contributions(user: User, campaign_id):
        campaign = CampaignService.get(user, campaign_id)
        return Contribution.objects.filter(
            campaign=campaign, payment__status=Payment.Status.APPROVED
        ).select_related("payment", "user")

    @staticmethod
    def contribute(
        user: User,
        campaign_id,
        amount: Decimal,
        cpf: str,
        name: str,
        message: str,
        anonymous: bool,
        notification_url: str,
    ) -> dict:
        """Charge a PIX through the payments module and link it to the campaign."""
        campaign = CampaignService.get(user, campaign_id)
        if campaign.status != Campaign.Status.ACTIVE:
            raise ValidationError(MSG_CAMPAIGN_CLOSED)
        if campaign.deadline and campaign.deadline < timezone.localdate():
            raise ValidationError(MSG_CAMPAIGN_EXPIRED)

        payment = Payment.objects.create(
            user=user,
            title=campaign.title[:255],
            amount=amount,
            payer_cpf=cpf,
            payer_name=name.strip(),
        )
        first_name, _, last_name = payment.payer_name.partition(" ")
        data = PaymentService._create_at_provider(
            payment,  # deleted by the service when the provider fails
            {
                "transaction_amount": float(amount),
                "description": campaign.title,
                "payment_method_id": "pix",
                "payer": {
                    "email": user.email,
                    "first_name": first_name,
                    "last_name": last_name or first_name,
                    "identification": {"type": "CPF", "number": cpf},
                },
                "external_reference": str(payment.id),
                "notification_url": notification_url,
            },
        )
        pix = data.get("point_of_interaction", {}).get("transaction_data", {})
        payment.provider_payment_id = str(data.get("id", ""))
        payment.status = data.get("status", Payment.Status.PENDING)
        payment.qr_code = pix.get("qr_code", "")
        payment.qr_code_base64 = pix.get("qr_code_base64", "")
        payment.ticket_url = pix.get("ticket_url", "")
        with transaction.atomic():
            payment.save()
            contribution = Contribution.objects.create(
                campaign=campaign,
                payment=payment,
                user=user,
                message=message,
                anonymous=anonymous,
            )
        return {
            "contribution_id": contribution.id,
            "payment_id": payment.id,
            "status": payment.status,
            "qr_code": payment.qr_code,
            "qr_code_base64": payment.qr_code_base64,
            "ticket_url": payment.ticket_url,
        }

    @staticmethod
    def contribution_status(user: User, contribution_id) -> Contribution:
        """My contribution with a payment refreshed from Mercado Pago while pending."""
        contribution = (
            Contribution.objects.select_related("payment")
            .filter(id=contribution_id, user=user)
            .first()
        )
        if contribution is None:
            raise NotFound(MSG_CAMPAIGN_NOT_FOUND)
        payment = contribution.payment
        if payment.status in (Payment.Status.PENDING, Payment.Status.IN_PROCESS):
            PaymentService.sync_payment(payment)
            payment.refresh_from_db()
        return contribution
