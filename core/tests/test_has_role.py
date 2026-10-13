from django.contrib.auth.models import AnonymousUser, Group
from django.test import TestCase
from rest_framework.test import APIRequestFactory

from core.models.user import User
from core.permissions.has_role import HasRole


class DummyView:
    required_roles = ["manager"]


class HasRoleTests(TestCase):
    def setUp(self):
        self.request = APIRequestFactory().get("/")
        self.user = User.objects.create_user("a@a.com", "pass", name="A")

    def check(self, user):
        self.request.user = user
        return HasRole().has_permission(self.request, DummyView())

    def test_anonymous_is_denied(self):
        self.assertFalse(self.check(AnonymousUser()))

    def test_user_without_role_is_denied(self):
        self.assertFalse(self.check(self.user))

    def test_user_with_role_is_allowed(self):
        self.user.groups.add(Group.objects.create(name="manager"))
        self.assertTrue(self.check(self.user))

    def test_superuser_is_allowed(self):
        self.user.is_superuser = True
        self.assertTrue(self.check(self.user))
