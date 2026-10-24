from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.utils import timezone

from core.modules.crowdfunding.models.campaign import Campaign, Contribution
from core.modules.kanban.tests.helpers import API, KanbanTestCase, client_for, make_user
from core.modules.payments.models.payment import Payment


class CrowdfundingTestCase(KanbanTestCase):
    def setUp(self):
        super().setUp()
        self.sdk = (
            mock.patch("core.modules.payments.services.payment._sdk")
            .start()
            .return_value
        )
        self.addCleanup(mock.patch.stopall)
        self.sdk.payment().create.return_value = {
            "status": 201,
            "response": {
                "id": 77,
                "status": "pending",
                "point_of_interaction": {
                    "transaction_data": {"qr_code": "000201", "qr_code_base64": "abc"}
                },
            },
        }

    def list_url(self):
        return f"{API}organizations/{self.org.id}/campaigns/"

    def make_campaign(self, **extra):
        res = self.client.post(
            self.list_url(), {"title": "Party", "goal_amount": "100.00", **extra}
        )
        self.assertEqual(res.status_code, 201, res.content)
        return res.json()

    def contribute(self, campaign_id, client=None, **extra):
        return (client or self.member_client).post(
            f"{API}campaigns/{campaign_id}/contributions/",
            {
                "amount": "25.50",
                "cpf": "123.456.789-01",
                "name": "Maria Silva",
                **extra,
            },
        )

    def approve(self):
        payment = Payment.objects.get()
        payment.status = Payment.Status.APPROVED
        payment.save()


class CampaignTests(CrowdfundingTestCase):
    def test_admin_creates_and_members_see_zero_raised(self):
        campaign = self.make_campaign()
        self.assertEqual(Decimal(campaign["raised"]), 0)
        res = self.member_client.get(self.list_url())
        self.assertEqual([c["title"] for c in res.json()["results"]], ["Party"])

    def test_plain_member_cannot_create(self):
        res = self.member_client.post(
            self.list_url(), {"title": "Nope", "goal_amount": "10.00"}
        )
        self.assertEqual(res.status_code, 403)

    def test_outsider_gets_404(self):
        campaign = self.make_campaign()
        outsider = client_for(make_user("out@a.com"))
        self.assertEqual(outsider.get(self.list_url()).status_code, 404)
        res = outsider.get(f"{API}campaigns/{campaign['id']}/")
        self.assertEqual(res.status_code, 404)

    def test_past_deadline_is_rejected(self):
        past = str(timezone.localdate() - timedelta(days=1))
        res = self.client.post(
            self.list_url(), {"title": "Old", "goal_amount": "10", "deadline": past}
        )
        self.assertEqual(res.status_code, 400)

    def test_contribution_charges_the_chosen_amount_and_counts_only_when_approved(self):
        campaign = self.make_campaign()
        res = self.contribute(campaign["id"])
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(res.data["qr_code"], "000201")

        payment = Payment.objects.get()
        self.assertEqual(payment.amount, Decimal("25.50"))
        self.assertEqual(payment.payer_cpf, "12345678901")
        self.assertEqual(
            self.sdk.payment().create.call_args.args[0]["transaction_amount"], 25.5
        )

        detail = f"{API}campaigns/{campaign['id']}/"
        self.sdk.payment().get.return_value = {"status": 200, "response": {}}
        self.assertEqual(Decimal(self.client.get(detail).json()["raised"]), 0)

        self.approve()
        body = self.client.get(detail).json()
        self.assertEqual(Decimal(body["raised"]), Decimal("25.50"))
        self.assertEqual(body["contributors"], 1)

    def test_anonymous_contribution_hides_the_name(self):
        campaign = self.make_campaign()
        self.contribute(campaign["id"], anonymous=True, message="Good luck")
        self.approve()
        res = self.client.get(f"{API}campaigns/{campaign['id']}/contributions/")
        item = res.json()["results"][0]
        self.assertIsNone(item["contributor_name"])
        self.assertEqual(item["message"], "Good luck")

    def test_pending_contributions_are_not_listed(self):
        campaign = self.make_campaign()
        self.contribute(campaign["id"])
        res = self.client.get(f"{API}campaigns/{campaign['id']}/contributions/")
        self.assertEqual(res.json()["results"], [])

    def test_amount_below_minimum_and_bad_cpf_are_rejected(self):
        campaign = self.make_campaign()
        self.assertEqual(
            self.contribute(campaign["id"], amount="0.50").status_code, 400
        )
        self.assertEqual(self.contribute(campaign["id"], cpf="123").status_code, 400)
        self.assertFalse(Payment.objects.exists())

    def test_closed_campaign_refuses_contributions(self):
        campaign = self.make_campaign()
        res = self.client.patch(
            f"{API}campaigns/{campaign['id']}/", {"status": "closed"}
        )
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(self.contribute(campaign["id"]).status_code, 400)

    def test_expired_campaign_refuses_contributions(self):
        campaign = self.make_campaign()
        Campaign.objects.filter(id=campaign["id"]).update(
            deadline=timezone.localdate() - timedelta(days=1)
        )
        self.assertEqual(self.contribute(campaign["id"]).status_code, 400)

    def test_provider_failure_leaves_no_payment_or_contribution(self):
        campaign = self.make_campaign()
        self.sdk.payment().create.return_value = {"status": 500}
        res = self.contribute(campaign["id"])
        self.assertEqual(res.status_code, 500)
        self.assertFalse(Payment.objects.exists())
        self.assertFalse(Contribution.objects.exists())

    def test_member_cannot_edit(self):
        campaign = self.make_campaign()
        res = self.member_client.patch(
            f"{API}campaigns/{campaign['id']}/", {"title": "x"}
        )
        self.assertEqual(res.status_code, 403)


class TaskCampaignTests(CrowdfundingTestCase):
    def setUp(self):
        super().setUp()
        self.sector = self.make_sector()
        self.task = self.make_task(self.sector)

    def url(self):
        return f"{API}tasks/{self.task['id']}/campaigns/"

    def test_charge_is_attached_to_the_task_and_hidden_from_the_org_list(self):
        res = self.client.post(self.url(), {"title": "Invoice", "goal_amount": "480"})
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(res.json()["task_id"], self.task["id"])
        self.assertFalse(res.json()["paid"])
        listed = self.client.get(self.url()).json()["results"]
        self.assertEqual([c["title"] for c in listed], ["Invoice"])
        org = self.client.get(self.list_url()).json()["results"]
        self.assertEqual(org, [])

    def test_sector_viewer_cannot_attach_but_can_see(self):
        viewer = self.add_org_member("viewer@a.com", "member")
        self.share_sector(self.sector, viewer, "viewer")
        viewer_client = client_for(viewer)
        res = viewer_client.post(self.url(), {"title": "x", "goal_amount": "10"})
        self.assertEqual(res.status_code, 403)
        self.client.post(self.url(), {"title": "Invoice", "goal_amount": "10"})
        self.assertEqual(viewer_client.get(self.url()).status_code, 200)

    def test_org_member_without_sector_access_gets_404(self):
        self.client.post(self.url(), {"title": "Invoice", "goal_amount": "10"})
        self.assertEqual(self.member_client.get(self.url()).status_code, 404)

    def test_paid_flag_and_contribution_result_follow_the_payment(self):
        campaign = self.client.post(
            self.url(), {"title": "Invoice", "goal_amount": "25.50"}
        ).json()
        res = self.contribute(campaign["id"], client=self.client)
        status_url = f"{API}contributions/{res.data['contribution_id']}/"

        self.sdk.payment().get.return_value = {
            "status": 200,
            "response": {
                "id": 77,
                "external_reference": str(res.data["payment_id"]),
                "status": "rejected",
            },
        }
        self.assertEqual(self.client.get(status_url).json()["result"], "rejected")
        self.assertFalse(
            self.client.get(f"{API}campaigns/{campaign['id']}/").json()["paid"]
        )

        Payment.objects.update(status=Payment.Status.APPROVED)
        self.assertEqual(self.client.get(status_url).json()["result"], "approved")
        self.assertTrue(
            self.client.get(f"{API}campaigns/{campaign['id']}/").json()["paid"]
        )

    def test_pending_result_and_only_the_payer_can_read_it(self):
        campaign = self.client.post(
            self.url(), {"title": "Invoice", "goal_amount": "50"}
        ).json()
        res = self.contribute(campaign["id"], client=self.client)
        status_url = f"{API}contributions/{res.data['contribution_id']}/"
        self.sdk.payment().get.return_value = {"status": 200, "response": {}}
        self.assertEqual(self.client.get(status_url).json()["result"], "pending")
        self.assertEqual(self.member_client.get(status_url).status_code, 404)
