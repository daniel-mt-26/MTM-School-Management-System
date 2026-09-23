"""Transactional platform-operator actions.  Secrets never leave this layer."""

import secrets
import string

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction

from .models import School, SchoolAdministrator, User


def generate_temporary_password(length=20):
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    # Guarantee each character class while keeping the password unguessable.
    required = [secrets.choice(string.ascii_lowercase), secrets.choice(string.ascii_uppercase), secrets.choice(string.digits), secrets.choice("!@#$%^&*")]
    remaining = [secrets.choice(alphabet) for _ in range(length - len(required))]
    values = required + remaining
    secrets.SystemRandom().shuffle(values)
    return "".join(values)


def validate_new_password(password, user):
    try:
        validate_password(password, user)
    except ValidationError as exc:
        raise ValidationError({"new_password": exc.messages}) from exc


@transaction.atomic
def provision_school(*, school_data, admin_data, password=None):
    """Create a school and exactly one linked administrator as one unit."""
    school = School(**school_data, status=School.Status.ACTIVE, is_active=True)
    user = User(
        username=admin_data["username"], email=admin_data.get("email", ""),
        first_name=admin_data.get("first_name", ""), last_name=admin_data.get("last_name", ""),
        role=User.Role.SCHOOL_ADMIN, must_change_password=True,
    )
    temporary_password = generate_temporary_password() if password is None else password
    validate_new_password(temporary_password, user)
    user.set_password(temporary_password)
    school.full_clean()
    user.full_clean()
    school.save()
    user.save()
    administrator = SchoolAdministrator(user=user, school=school)
    administrator.full_clean()
    administrator.save()
    return school, administrator, temporary_password


@transaction.atomic
def create_school_administrator(*, school, admin_data):
    user = User(
        username=admin_data["username"], email=admin_data.get("email", ""),
        first_name=admin_data.get("first_name", ""), last_name=admin_data.get("last_name", ""),
        role=User.Role.SCHOOL_ADMIN, must_change_password=True,
    )
    temporary_password = generate_temporary_password()
    user.set_password(temporary_password)
    user.full_clean()
    user.save()
    administrator = SchoolAdministrator(user=user, school=school)
    administrator.full_clean()
    administrator.save()
    return administrator, temporary_password


@transaction.atomic
def reset_administrator_password(administrator):
    user = administrator.user
    temporary_password = generate_temporary_password()
    user.set_password(temporary_password)
    user.must_change_password = True
    user.token_version += 1
    user.save(update_fields=["password", "must_change_password", "token_version"])
    return temporary_password
