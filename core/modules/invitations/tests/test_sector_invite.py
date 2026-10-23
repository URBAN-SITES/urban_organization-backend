import re
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from django.core import mail
from django.test import TestCase
from rest_framework.exceptions import ValidationError

from core.models.user import User
from core.modules.invitations.models.invite import OrganizationInvite
from core.modules.invitations.services.invite import InviteService
from core.modules.kanban.models.sector import SectorMember
from core.modules.kanban.services.sector import SectorService
from core.modules.organizations.services.organization import OrganizationService


class SectorInviteTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email="sector-owner@example.invalid", password="Sector-test!2026"
        )
        self.guest = User.objects.create_user(
            email="sector-guest@example.invalid", password="Sector-test!2026"
        )
        self.org = OrganizationService.create(self.owner, name="Norte")
        self.sector = SectorService.create(self.owner, self.org.pk, name="Design")

    def invite(self, role="member"):
        with self.captureOnCommitCallbacks(execute=True):
            invitation = InviteService.create(
                self.owner,
                self.org.pk,
                self.guest.email,
                role,
                sector_ids=[self.sector.pk],
            )
        token = parse_qs(
            urlparse(re.search(r"https?://\S+", mail.outbox[-1].body).group()).query
        )["token"][0]
        return invitation, token

    def test_accept_applies_sector_access_only_after_acceptance(self):
        invitation, token = self.invite()
        self.assertEqual(list(invitation.sectors.all()), [self.sector])
        self.assertFalse(
            SectorMember.objects.filter(sector=self.sector, user=self.guest).exists()
        )
        InviteService.accept(self.guest, token)
        self.assertEqual(
            SectorService.effective_role(self.guest, self.sector), "editor"
        )
        with self.assertRaises(ValidationError):
            InviteService.accept(self.guest, token)

    def test_viewer_invite_only_grants_viewer_access(self):
        _, token = self.invite("viewer")
        InviteService.accept(self.guest, token)
        self.assertEqual(
            SectorService.effective_role(self.guest, self.sector), "viewer"
        )

    def test_sectors_from_other_organizations_are_rejected(self):
        other = OrganizationService.create(self.owner, name="Other")
        foreign_sector = SectorService.create(self.owner, other.pk, name="Private")
        with self.assertRaises(ValidationError):
            InviteService.create(
                self.owner,
                self.org.pk,
                self.guest.email,
                "member",
                sector_ids=[foreign_sector.pk],
            )
        self.assertFalse(OrganizationInvite.objects.exists())

    def test_revoked_or_deleted_sector_is_not_granted(self):
        invitation, token = self.invite()
        self.sector.soft_delete()
        InviteService.accept(self.guest, token)
        self.assertFalse(
            SectorMember.objects.filter(sector=self.sector, user=self.guest).exists()
        )
        self.assertEqual(
            OrganizationInvite.objects.get(pk=invitation.pk).status, "accepted"
        )

    def test_sector_assignment_failure_rolls_back_acceptance(self):
        invitation, token = self.invite()
        with patch(
            "core.modules.invitations.services.invite.SectorMember.objects.get_or_create",
            side_effect=RuntimeError("Failure"),
        ):
            with self.assertRaises(RuntimeError):
                InviteService.accept(self.guest, token)
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, "pending")
        self.assertFalse(self.org.members.filter(user=self.guest).exists())
