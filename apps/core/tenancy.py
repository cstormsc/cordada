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
        self.assign_client()
        super().save(*args, **kwargs)

    def assign_client(self):
        """Sets client from the current one; refuses rows of another client."""
        current = _require_client()
        if self.client_id is None:
            self.client = current
        elif self.client_id != current.pk:
            raise NoCurrentClient(
                f"{type(self).__name__} pertenece a otro cliente que el activo."
            )


def assign_next_number(instance, field="numero"):
    """Gives a new row the next per-client number. Call inside save() before insert."""
    from django.db import transaction
    from django.db.models import Max

    from .models import Client

    if getattr(instance, field):
        return
    instance.assign_client()
    with transaction.atomic():
        # Lock the client row so concurrent creates get consecutive numbers.
        Client.objects.select_for_update().filter(pk=instance.client_id).first()
        model = type(instance)
        last = model.unscoped.filter(client_id=instance.client_id).aggregate(n=Max(field))["n"]
        setattr(instance, field, (last or 0) + 1)
