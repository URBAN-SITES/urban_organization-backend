import os
from unittest import mock

from cryptography.fernet import Fernet
from django.test import SimpleTestCase

from core.models.fields import EncryptedTextField, _fernet


@mock.patch.dict(os.environ, {"FIELD_ENCRYPTION_KEY": Fernet.generate_key().decode()})
class EncryptedTextFieldTests(SimpleTestCase):
    def setUp(self):
        _fernet.cache_clear()
        self.field = EncryptedTextField()

    def test_round_trip(self):
        stored = self.field.get_prep_value("secret")
        self.assertNotEqual(stored, "secret")
        self.assertEqual(self.field.from_db_value(stored, None, None), "secret")

    def test_empty_values_are_kept(self):
        self.assertIsNone(self.field.get_prep_value(None))
        self.assertEqual(self.field.get_prep_value(""), "")
