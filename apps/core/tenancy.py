"""Shared-database multi-tenancy.

Every client-scoped model inherits TenantScopedModel. Its default manager only
returns rows for the *current client*, which the ClientMiddleware sets for
requests under /c/<slug>/ and code outside requests sets with tenant_context().
Querying with no current client raises instead of silently returning every
client's data. Use Model.unscoped for deliberate cross-client access.
"""

from contextlib import contextmanager
from contextvars import ContextVar

from django.db import models

_current_client = ContextVar("current_client", default=None)


class NoCurrentClient(RuntimeError):
    pass


def get_current_client():
    return _current_client.get()


def set_current_client(client):
    """Returns a token for reset_current_client()."""
    return _current_client.set(client)


def reset_current_client(token):
    _current_client.reset(token)


@contextmanager
def tenant_context(client):
    token = set_current_client(client)
    try:
        yield client
    finally:
        reset_current_client(token)


def _require_client():
    client = get_current_client()
    if client is None:
        raise NoCurrentClient(
            "No hay cliente activo. Usa tenant_context(cliente) o Model.unscoped."
        )
    return client


class TenantManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(client=_require_client())


class TenantScopedModel(models.Model):
    client = models.ForeignKey("core.Client", on_delete=models.PROTECT, related_name="+",
                               editable=False)

    objects = TenantManager()
    unscoped = models.Manager()  # noqa: DJ012 (fields in subclasses come after these)

    class Meta:
        abstract = True
        # Plain manager for internal lookups (FK access, deletes); objects stays scoped.
        base_manager_name = "unscoped"

    def save(self, *args, **kwargs):
        current = _require_client()
        if self.client_id is None:
            self.client = current
        elif self.client_id != current.pk:
            raise NoCurrentClient(
                f"{type(self).__name__} pertenece a otro cliente que el activo."
            )
        super().save(*args, **kwargs)
