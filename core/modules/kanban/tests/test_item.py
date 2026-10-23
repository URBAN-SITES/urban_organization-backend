from core.modules.kanban.tests.helpers import (
    API,
    KanbanTestCase,
    client_for,
    make_user,
)
from core.modules.notifications.models.notification import Notification


class ItemTests(KanbanTestCase):
    def setUp(self):
        super().setUp()
        self.sector_id = self.make_sector()
        self.share_sector(self.sector_id, self.member, "editor")
        self.task = self.make_task(self.sector_id)
        self.base = f"{API}tasks/{self.task['id']}/"

    def test_checklist_crud_and_roles(self):
        url = f"{self.base}checklist/"
        first = self.client.post(url, {"content": "Draft"}).json()
        second = self.client.post(url, {"content": "Review"}).json()
        self.assertEqual((first["position"], second["position"]), (0, 1))
        res = self.client.patch(f"{url}{first['id']}/", {"is_done": True})
        self.assertTrue(res.json()["is_done"])
        self.assertEqual(self.client.delete(f"{url}{second['id']}/").status_code, 204)
        self.assertEqual(len(self.client.get(url).json()["results"]), 1)
        viewer = self.add_org_member("v@a.com")
        self.share_sector(self.sector_id, viewer, "viewer")
        viewer_client = client_for(viewer)
        self.assertEqual(viewer_client.get(url).status_code, 200)
        self.assertEqual(viewer_client.post(url, {"content": "x"}).status_code, 403)

    def test_comments_have_author_and_notify_the_assignee(self):
        self.client.patch(f"{self.base}", {"assignee": str(self.member.id)})
        Notification.objects.all().delete()
        url = f"{self.base}comments/"
        res = self.client.post(url, {"content": "Please check"})
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.json()["author_id"], str(self.owner.id))
        self.assertEqual(Notification.objects.filter(user=self.member).count(), 1)
        # the assignee commenting does not notify themselves
        self.member_client.post(url, {"content": "On it"})
        self.assertEqual(Notification.objects.filter(user=self.member).count(), 1)
        self.assertEqual(len(self.client.get(url).json()["results"]), 2)

    def test_comment_edit_is_author_only_and_manager_can_delete(self):
        url = f"{self.base}comments/"
        comment = self.member_client.post(url, {"content": "Mine"}).json()
        detail = f"{url}{comment['id']}/"
        self.assertEqual(self.client.patch(detail, {"content": "x"}).status_code, 403)
        res = self.member_client.patch(detail, {"content": "Edited"})
        self.assertEqual(res.json()["content"], "Edited")
        other = self.add_org_member("o@a.com")
        self.share_sector(self.sector_id, other, "editor")
        self.assertEqual(client_for(other).delete(detail).status_code, 403)
        self.assertEqual(self.client.delete(detail).status_code, 204)  # manager
        self.assertEqual(self.client.post(url, {"content": ""}).status_code, 400)

    def test_links_on_task_sector_and_organization(self):
        body = {"title": "Spec", "url": "https://example.com/spec"}
        targets = {
            "task": f"{self.base}links/",
            "sector": f"{API}sectors/{self.sector_id}/links/",
            "organization": f"{API}organizations/{self.org.id}/links/",
        }
        for name, url in targets.items():
            res = self.client.post(url, body)
            self.assertEqual(res.status_code, 201, name)
            self.assertEqual(len(self.client.get(url).json()["results"]), 1, name)
        self.assertEqual(
            self.client.post(targets["task"], {"url": "nope"}).status_code, 400
        )
        outsider = client_for(make_user("out@a.com"))
        self.assertEqual(outsider.get(targets["organization"]).status_code, 404)

    def test_link_delete_permissions(self):
        url = f"{self.base}links/"
        link = self.member_client.post(url, {"url": "https://a.com"}).json()
        other = self.add_org_member("o@a.com")
        self.share_sector(self.sector_id, other, "editor")
        detail = f"{API}links/{link['id']}/"
        self.assertEqual(client_for(other).delete(detail).status_code, 403)
        self.assertEqual(self.member_client.delete(detail).status_code, 204)  # creator
        link = self.member_client.post(url, {"url": "https://b.com"}).json()
        self.assertEqual(
            self.client.delete(f"{API}links/{link['id']}/").status_code, 204
        )
        self.assertEqual(
            self.client.delete(f"{API}links/{link['id']}/").status_code, 404
        )
