from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords

from apps.catalogs.models import GrupoImpactado
from apps.core.tenancy import TenantScopedModel


class IndicadorConfig(TenantScopedModel):
    """Per-client settings for one indicator (thresholds are still to be defined, §13.3)."""

    key = models.CharField(max_length=40)
    verde = models.DecimalField(
        _("en meta desde"), max_digits=8, decimal_places=2, null=True, blank=True
    )
    amarillo = models.DecimalField(
        _("atención desde"), max_digits=8, decimal_places=2, null=True, blank=True
    )
    responsable = models.CharField(_("responsable"), max_length=150, blank=True)
    frecuencia = models.CharField(_("frecuencia"), max_length=60, blank=True)
    activo = models.BooleanField(_("se muestra"), default=True)

    history = HistoricalRecords()

    class Meta(TenantScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["client", "key"], name="unique_indicador_config"),
        ]


class ValorManual(TenantScopedModel):
    """Data that does not come from the platform (§8): active users, adoption, surveys."""

    key = models.CharField(max_length=40)
    fecha = models.DateField(_("fecha del dato"))
    valor = models.DecimalField(_("valor"), max_digits=10, decimal_places=2)
    grupo = models.ForeignKey(
        GrupoImpactado,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("grupo"),
        help_text=_("Vacío: dato de toda la organización."),
    )
    nota = models.CharField(_("nota o fuente"), max_length=300, blank=True)
    cargado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantScopedModel.Meta):
        ordering = ["-fecha", "-created_at"]
