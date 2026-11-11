from .base import *  # noqa: F403

# On by default for development; DJANGO_DEBUG=false when others can reach the site (a
# tunnel), so an error never shows them code or settings.
DEBUG = env.bool("DJANGO_DEBUG", default=True)  # noqa: F405

# No collectstatic here: serve static files straight from the source folders.
WHITENOISE_USE_FINDERS = True
WHITENOISE_AUTOREFRESH = True
