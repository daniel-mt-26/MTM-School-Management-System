"""Local PostgreSQL test certification; faster hashing for disposable test users only."""
from .settings import *  # noqa: F403

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
TEST_RUNNER = "config.test_runner.IsolatedCacheRunner"
