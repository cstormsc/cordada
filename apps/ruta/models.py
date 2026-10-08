import datetime

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords

from apps.catalogs.models import Canal, GrupoImpactado, SystemCatalog, SystemCatalogField
from apps.core.attachments import AbstractAdjunto
from apps.core.tenancy import TenantManager, TenantScopedModel, assign_next_number
from apps.matriz.models import Impacto


class EstadoActividad(models.TextChoices):
    NO_INICIADO = "no_iniciado", _("No iniciado")
    EN_CURSO = "en_curso", _("En curso")
    COMPLETADO = "completado", _("Completado")
    VERIFICADO = "verificado", _("Verificado")


DONE = (EstadoActividad.COMPLETADO, EstadoActividad.VERIFICADO)


class Cumplimiento(models.TextChoices):
    A_TIEMPO = "a_tiempo", _("Hecha a tiempo")
    CON_RETRASO = "con_retraso", _("Hecha con retraso")
    NO_REALIZADA = "no_realizada", _("No realizada")
    NO_PLANIFICADA = "no_planificada", _("No planificada")
    PENDIENTE = "pendiente", _("Pendiente")


def cumplimiento(*, no_planificada, estado, fecha_planificada, fecha_real, today):
    """§5 compliance for one activity. Mirrored in ActividadQuerySet.with_cumplimiento()."""
    if no_planificada:
        return Cumplimiento.NO_PLANIFICADA
    if estado in DONE and fecha_real and fecha_planificada:
        return (Cumplimiento.A_TIEMPO if fecha_real <= fecha_planificada
                else Cumplimiento.CON_RETRASO)
    if estado not in DONE and fecha_planificada and fecha_planificada < today:
        return Cumplimiento.NO_REALIZADA
    return Cumplimiento.PENDIENTE


class ActividadQuerySet(models.QuerySet):
    def with_cumplimiento(self, today=None):
        today = today or timezone.localdate()
        C, W, V = models.Case, models.When, models.Value
        return self.annotate(cumplimiento=C(
            W(no_planificada=True, then=V(Cumplimiento.NO_PLANIFICADA)),
            W(estado__in=DONE, fecha_real__isnull=False, fecha_planificada__isnull=False,
              fecha_real__lte=models.F("fecha_planificada"), then=V(Cumplimiento.A_TIEMPO)),
            W(estado__in=DONE, fecha_real__isnull=False, fecha_planificada__isnull=False,
              then=V(Cumplimiento.CON_RETRASO)),
            W(~models.Q(estado__in=DONE), fecha_planificada__lt=today,
              then=V(Cumplimiento.NO_REALIZADA)),
            default=V(Cumplimiento.PENDIENTE),
            output_field=models.CharField(),
        ))

    def huerfanas(self):
        return self.filter(impactos__isnull=True)

    def of_groups(self, grupos):
        return self.filter(grupos__in=grupos).distinct()


class Actividad(TenantScopedModel):
    numero = models.PositiveIntegerField(_("ID"), editable=False)
    titulo = models.CharField(_("actividad"), max_length=200)
    descripcion = models.TextField(_("descripción"), blank=True)
    frente = SystemCatalogField(SystemCatalog.FRENTE, verbose_name=_("frente"))
    tiempo = SystemCatalogField(SystemCatalog.TIEMPO, verbose_name=_("tiempo del marco"),
                                null=True, blank=True)
    grupos = models.ManyToManyField(GrupoImpactado, blank=True, related_name="actividades",
                                    verbose_name=_("grupos impactados"))
    impactos = models.ManyToManyField(
        Impacto, blank=True, related_name="actividades", verbose_name=_("impactos"),
        help_text=_("Impactos de la matriz a los que responde. Sin impacto, la actividad "
                    "queda marcada como huérfana."),
    )
    responsable = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                    null=True, blank=True, related_name="+",
                                    verbose_name=_("responsable"))
    no_planificada = models.BooleanField(
        _("no planificada"), default=False,
        help_text=_("Marca si surgió sobre la marcha y no estaba en el plan."),
    )
    fecha_planificada = models.DateField(_("fecha planificada"), null=True, blank=True)
    fecha_real = models.DateField(_("fecha real"), null=True, blank=True,
                                  help_text=_("Cuándo se hizo."))
    estado = models.CharField(_("estado"), max_length=20, choices=EstadoActividad.choices,
                              default=EstadoActividad.NO_INICIADO)
    canal = models.ForeignKey(Canal, on_delete=models.PROTECT, null=True, blank=True,
                              related_name="+", verbose_name=_("canal o formato"))
    vocero = models.CharField(
        _("líder o vocero"), max_length=150, blank=True,
        help_text=_("En comunicaciones: quién firma o da el mensaje."),
    )
    evidencia = models.TextField(
        _("evidencia"), blank=True,
        help_text=_("Qué demuestra que se hizo: asistentes, alcance, respuestas. "
                    "Adjunta archivos o enlaces en el detalle."),
    )
    indicador = models.CharField(_("indicador asociado"), max_length=200, blank=True)
    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                       related_name="+", editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager.from_queryset(ActividadQuerySet)()
    history = HistoricalRecords(excluded_fields=["updated_at"], m2m_fields=[grupos, impactos])

    class Meta(TenantScopedModel.Meta):
        verbose_name = _("actividad")
        verbose_name_plural = _("actividades")
        ordering = ["fecha_planificada", "numero"]
        constraints = [
            models.UniqueConstraint(fields=["client", "numero"], name="unique_actividad_numero"),
        ]

    def __str__(self):
        return f"{self.codigo} {self.titulo}"

    @property
    def codigo(self):
        return f"ACT-{self.numero:03d}" if self.numero else "ACT-nueva"

    @property
    def es_comunicacion(self):
        return self.frente.code == "comunicacion" if self.frente_id else False

    def get_cumplimiento(self, today: datetime.date | None = None):
        return Cumplimiento(cumplimiento(
            no_planificada=self.no_planificada, estado=self.estado,
            fecha_planificada=self.fecha_planificada, fecha_real=self.fecha_real,
            today=today or timezone.localdate(),
        ))

    def save(self, *args, **kwargs):
        with transaction.atomic():
            assign_next_number(self)
            super().save(*args, **kwargs)


class Evidencia(AbstractAdjunto):
    UPLOAD_DIR = "actividades"

    actividad = models.ForeignKey(Actividad, on_delete=models.CASCADE, related_name="adjuntos")

    class Meta(AbstractAdjunto.Meta):
        pass
