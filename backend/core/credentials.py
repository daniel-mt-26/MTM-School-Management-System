import secrets
import unicodedata
import re
from django.db import IntegrityError, transaction
from .models import User


def temporary_password():
    return secrets.token_urlsafe(18)


def create_login(*, role, first_name="", last_name="", email="", username=""):
    base = username or re.sub(r"[^a-z0-9.]", "", unicodedata.normalize("NFKD", f"{first_name}.{last_name}").encode("ascii", "ignore").decode().lower()).strip(".") or role
    base = base[:130]
    password = temporary_password()
    for suffix in range(1, 10000):
        candidate = base if suffix == 1 else f"{base}{suffix}"
        try:
            with transaction.atomic():
                user = User.objects.create_user(username=candidate, password=password, role=role,
                    first_name=first_name, last_name=last_name, email=email, must_change_password=True)
            return user, password
        except IntegrityError:
            if not User.objects.filter(username=candidate).exists():
                raise
    raise ValueError("Unable to allocate a unique username.")


def reset_login(user):
    password = temporary_password()
    user.set_password(password)
    user.token_version += 1
    user.must_change_password = True
    user.save(update_fields=["password", "token_version", "must_change_password"])
    return password
