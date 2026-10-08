from django.db import models

from apps.catalogs.models import SystemCatalog, SystemCatalogField
from apps.core.tenancy import TenantScopedModel


class Note(TenantScopedModel):
    """Test-only client-scoped model (installed only in test settings)."""

    text = models.CharField(max_length=100)
    tipo = SystemCatalogField(SystemCatalog.TIPO_IMPACTO, null=True, blank=True)
