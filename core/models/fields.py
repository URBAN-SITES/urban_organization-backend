import os
from functools import cache

from cryptography.fernet import Fernet
from django.db import models


@cache
def _fernet() -> Fernet:
    # generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    return Fernet(os.environ["FIELD_ENCRYPTION_KEY"])


class EncryptedTextField(models.TextField):
    """
    Text encrypted at rest (AES via Fernet), transparent in Python code:
        cpf = EncryptedTextField()

    Ciphertext is random per save, so the column cannot be filtered, ordered
    or unique. Losing FIELD_ENCRYPTION_KEY makes the data unrecoverable.
    """

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if value is None or value == "":
            return value
        return _fernet().encrypt(value.encode()).decode()

    def from_db_value(self, value, expression, connection):
        if value is None or value == "":
            return value
        return _fernet().decrypt(value.encode()).decode()
