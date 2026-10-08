from .base import *  # noqa: F403

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

INSTALLED_APPS = [*INSTALLED_APPS, "apps.core.tests.tenantapp"]  # noqa: F405

import tempfile  # noqa: E402

MEDIA_ROOT = tempfile.mkdtemp(prefix="cordada-test-media-")
