from core.modules.github.models.github import GitHubProjectItem
from core.modules.github.tests.helpers import GitHubTestCase, response
from core.modules.kanban.models.task import Status, Task
from core.modules.kanban.tests.helpers import API, client_for


def item(id_, title, status=None, body="", archived=False, kind="Issue"):
    return {
        "id": id_,
        "isArchived": archived,
        "fieldValueByName": {"name": status} if status else None,
        "content": {
            "__typename": kind,
            "title": title,
            "body": body,
            "url": f"https://github.com/acme/api/issues/{id_}",
        },
    }


class GitHubProjectImportTests(GitHubTestCase):
    def setUp(self):
        super().setUp()
        self.connect()
        self.sector = self.make_sector()
        self.url = f"{API}sectors/{self.sector}/github/projects/import/"
        self.board = {
            "options": ["Todo", "In Progress", "Review", "Done"],
            "items": [
                item("I1", "Login page", "Todo", body="Build it"),
                item("I2", "API", "In Progress"),
                item("I3", "Old card", "Done", archived=True),
                item("I4", "Ship", "Done"),
                item("I5", "Sketch", None, kind="DraftIssue"),
            ],
        }
        self.github.on(
            "GET",
            "/user/installations",
            body={
                "total_count": 3,
                "installations": [
                    {"id": 1, "account": {"login": "octo", "type": "User"}},
                    {"id": 2, "account": {"login": "acme", "type": "Organization"}},
                    {
                        "id": 3,
                        "account": {"login": "closed-org", "type": "Organization"},
                    },
                ],
            },
        )
        self.github.on("POST", "/graphql")
        self.github.routes[("POST", "/graphql")] = self.graphql

    def graphql(self, json=None, **_kw):
        if "viewer" in json["query"]:
            return response(
                body={
                    "data": {
                        "viewer": {
                            "login": "octo",
                            "projectsV2": {
                                "nodes": [
                                    {
                                        "id": "PVT_1",
                                        "number": 1,
                                        "title": "Roadmap",
                                        "url": "https://github.com/users/octo/projects/1",
                                        "closed": False,
                                    }
                                ]
                            },
                        },
                        "o0": {
                            "login": "acme",
                            "projectsV2": {
                                "nodes": [
                                    {
                                        "id": "PVT_2",
                                        "number": 3,
                                        "title": "Sprint",
                                        "url": "https://github.com/orgs/acme/projects/3",
                                        "closed": False,
                                    }
                                ]
                            },
                        },
                        "o1": None,
                    },
                    # an org that blocks the app must not hide the user's own boards
                    "errors": [{"type": "FORBIDDEN", "message": "org blocks app"}],
                }
            )
        if json["variables"]["id"] != "PVT_1":
            return response(body={"data": {"node": None}})
        return response(
            body={
                "data": {
                    "node": {
                        "id": "PVT_1",
                        "title": "Roadmap",
                        "url": "https://github.com/users/octo/projects/1",
                        "field": {
                            "options": [{"name": n} for n in self.board["options"]]
                        },
                        "items": {
                            "pageInfo": {"hasNextPage": False, "endCursor": None},
                            "nodes": self.board["items"],
                        },
                    }
                }
            }
        )

    def import_board(self, project_id="PVT_1", client=None):
        return (client or self.client).post(
            self.url, {"project_id": project_id}, format="json"
        )

    def test_lists_the_boards_the_user_can_read(self):
        res = self.client.get(f"{API}integrations/github/projects/")
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(
            [(p["title"], p["owner"]) for p in res.json()],
            [("Roadmap", "octo"), ("Sprint", "acme")],
        )
        # the org boards come from the app's installations, one lookup per org
        query = self.github.calls[-1][2]["json"]
        self.assertEqual(query["variables"], {"o0": "acme", "o1": "closed-org"})

    def test_import_creates_columns_and_tasks_in_github_order(self):
        res = self.import_board()
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(
            res.json(),
            {
                "project": "Roadmap",
                "created": 4,
                "updated": 0,
                "columns_created": 1,  # Todo/In Progress/Done map to existing columns
                "skipped": 1,  # archived card
            },
        )
        tasks = {t.title: t for t in Task.objects.filter(sector_id=self.sector)}
        self.assertEqual(tasks["Login page"].status.name, "A fazer")
        self.assertEqual(tasks["Login page"].description, "Build it")
        self.assertEqual(tasks["API"].status.name, "Em andamento")
        self.assertEqual(tasks["Ship"].status.category, Status.Category.DONE)
        self.assertIsNotNone(tasks["Ship"].completed_at)
        self.assertTrue(
            Status.objects.filter(sector_id=self.sector, name="Review").exists()
        )
        self.assertNotIn("Old card", tasks)

    def test_importing_again_updates_instead_of_duplicating(self):
        self.import_board()
        self.board["items"][0] = item("I1", "Login page v2", "Done", body="Done!")
        self.board["items"].append(item("I6", "New card", "Review"))
        res = self.import_board()
        self.assertEqual(res.json()["created"], 1)
        self.assertEqual(res.json()["updated"], 1)
        self.assertEqual(res.json()["columns_created"], 0)
        login = GitHubProjectItem.objects.get(item_id="I1").task
        self.assertEqual(login.title, "Login page v2")
        self.assertEqual(login.status.category, Status.Category.DONE)
        self.assertEqual(Task.objects.filter(sector_id=self.sector).count(), 5)

    def test_permissions_and_unknown_board(self):
        self.assertEqual(self.import_board("PVT_missing").status_code, 404)
        viewer = client_for(self.member)
        self.share_sector(self.sector, self.member)  # editor, not manager
        self.assertIn(self.import_board(client=viewer).status_code, (403, 404))
        self.assertFalse(Task.objects.filter(sector_id=self.sector).exists())

    def test_missing_projects_permission_is_explained(self):
        self.github.routes[("POST", "/graphql")] = response(
            body={
                "errors": [{"type": "FORBIDDEN", "message": "Resource not accessible"}]
            }
        )
        res = self.import_board()
        self.assertEqual(res.status_code, 403)
        self.assertIn("Projects", res.json()["detail"])
