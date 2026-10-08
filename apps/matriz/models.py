from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords

from apps.catalogs.models import (
    CategoriaResponsable,
    GrupoImpactado,
    SystemCatalog,
    SystemCatalogField,
)
from apps.core.attachments import AbstractAdjunto
from apps.core.tenancy import TenantScopedModel, assign_next_number
from apps.scoring import rules


def scale_field(verbose_name, help_text):
    return models.PositiveSmallIntegerField(
        verbose_name,
        null=True,
        blank=True,
        help_text=help_text,
        validators=[MinValueValidator(1), MaxValueValidator(4)],
    )


def yes_no_field(verbose_name, help_text=""):
    """Null means 'not decided yet', which matters for the required-field check."""
    return models.BooleanField(verbose_name, null=True, blank=True, help_text=help_text)


class Estado(models.TextChoices):
    PROPUESTO = "propuesto", _("Propuesto")
    EVALUADO = "evaluado", _("Evaluado")
    EN_ATENCION = "en_atencion", _("En atención")
    ATENDIDO = "atendido", _("Atendido")
    CERRADO = "cerrado", _("Cerrado")
    DESCARTADO = "descartado", _("Descartado")
    REABIERTO = "reabierto", _("Reabierto")


# Impacts being worked on: they should have activities in the Ruta.
ACTIVE_STATES = (Estado.EVALUADO, Estado.EN_ATENCION, Estado.REABIERTO)


class CriticidadFormacion(models.TextChoices):
    # Provisional values: §4 names the field but not its scale.
    BAJA = "baja", _("Baja")
    MEDIA = "media", _("Media")
    ALTA = "alta", _("Alta")


def sin_criterio_q():
    return models.Q(criterio_evidencia__isnull=True) | models.Q(criterio_descripcion="")


class Impacto(TenantScopedModel):
    numero = models.PositiveIntegerField(_("ID"), editable=False)
    estado = models.CharField(
        _("estado"), max_length=20, choices=Estado.choices, default=Estado.PROPUESTO, editable=False
    )

    # Identificación
    titulo = models.CharField(
        _("título"),
        max_length=200,
        help_text=_("Una frase que nombre el cambio que vive el grupo."),
    )
    descripcion = models.TextField(
        _("descripción del impacto"),
        help_text=_(
            "Qué cambia para las personas, en su trabajo diario. Describe el efecto, "
            "no la solución."
        ),
    )
    situacion_actual = models.TextField(
        _("situación actual"), blank=True, help_text=_("Cómo se trabaja hoy.")
    )
    situacion_futura = models.TextField(
        _("situación futura"), blank=True, help_text=_("Cómo se trabajará después del cambio.")
    )
    origen = SystemCatalogField(
        SystemCatalog.ORIGEN,
        verbose_name=_("origen"),
        null=True,
        blank=True,
        help_text=_("Dónde o cómo se detectó el impacto."),
    )

    # Clasificación
    tipo = SystemCatalogField(
        SystemCatalog.TIPO_IMPACTO, verbose_name=_("tipo de impacto"), null=True, blank=True
    )
    tiempo = SystemCatalogField(
        SystemCatalog.TIEMPO,
        verbose_name=_("tiempo del marco"),
        null=True,
        blank=True,
        help_text=_("En qué tiempo se atiende."),
    )

    # Quién
    grupo = models.ForeignKey(
        GrupoImpactado,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="impactos",
        verbose_name=_("grupo impactado"),
    )
    grupo_sugerido = models.CharField(
        _("grupo sugerido"),
        max_length=150,
        blank=True,
        help_text=_(
            "Si el grupo no está en la lista, escríbelo aquí. El equipo de cambio "
            "lo agrega o lo asigna a uno existente."
        ),
    )
    personas_impactadas = models.PositiveIntegerField(
        _("personas impactadas"), null=True, blank=True
    )

    # Evaluación
    magnitud = scale_field(_("magnitud"), _("Cuánto cambia el trabajo del grupo."))
    resistencia = scale_field(_("resistencia esperada"), "")
    preparacion = scale_field(_("preparación del grupo"), "")

    # Riesgo
    riesgo_descripcion = models.TextField(
        _("descripción del riesgo"),
        blank=True,
        help_text=_("Qué podría salir mal si el impacto no se atiende."),
    )
    probabilidad = scale_field(_("probabilidad"), _("Qué tan probable es que el riesgo ocurra."))
    severidad = scale_field(
        _("severidad"), _("Qué tan grave sería si ocurre. Extrema siempre genera alerta.")
    )
    riesgo_puntaje = models.PositiveSmallIntegerField(
        _("puntaje de riesgo"), null=True, editable=False
    )
    riesgo_nivel = models.PositiveSmallIntegerField(
        _("nivel de riesgo"),
        null=True,
        editable=False,
        choices=[(b.value, b.label) for b in rules.RiskBand],
    )

    # Derivación
    requiere_comunicacion = yes_no_field(_("requiere comunicación"))
    requiere_movilizacion = yes_no_field(_("requiere movilización"))
    requiere_formacion = yes_no_field(_("requiere formación"))
    tipo_cambio_conocimiento = SystemCatalogField(
        SystemCatalog.TIPO_CAMBIO_CONOCIMIENTO,
        verbose_name=_("tipo de cambio en el conocimiento"),
        null=True,
        blank=True,
    )
    formacion_criticidad = models.CharField(
        _("criticidad de la formación"),
        max_length=10,
        choices=CriticidadFormacion.choices,
        blank=True,
    )
    formacion_momento = SystemCatalogField(
        SystemCatalog.TIEMPO,
        verbose_name=_("momento requerido de la formación"),
        null=True,
        blank=True,
        help_text=_("En qué tiempo del marco debe estar lista."),
    )

    # Mitigación y acción
    medida = models.TextField(
        _("medida de mitigación"), blank=True, help_text=_("Qué se hará para atender el impacto.")
    )
    responsable = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("responsable"),
    )
    responsable_categoria = models.ForeignKey(
        CategoriaResponsable,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("categoría del responsable"),
    )
    fecha_compromiso = models.DateField(_("fecha compromiso"), null=True, blank=True)

    # Cierre
    criterio_evidencia = SystemCatalogField(
        SystemCatalog.EVIDENCIA_CIERRE,
        verbose_name=_("tipo de evidencia de cierre"),
        null=True,
        blank=True,
        help_text=_(
            "Con qué se demostrará que el impacto está atendido. Se define al evaluar, no al final."
        ),
    )
    criterio_meta = models.DecimalField(
        _("meta"),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("Valor numérico a alcanzar, por ejemplo 90 (%) o 5 (tickets)."),
    )
    criterio_descripcion = models.CharField(
        _("descripción del criterio"), max_length=300, blank=True
    )
    requiere_certificacion_lider = models.BooleanField(
        _("requiere certificación del líder"),
        default=False,
        help_text=_("Si se marca, el líder del área aplica la evaluación práctica."),
    )

    # Prioridad
    prioridad_calculada = models.PositiveSmallIntegerField(
        _("prioridad calculada"),
        null=True,
        editable=False,
        choices=[(p.value, p.label) for p in rules.Priority],
    )
    prioridad_ajustada = models.PositiveSmallIntegerField(
        _("prioridad ajustada"),
        null=True,
        blank=True,
        choices=[(p.value, p.label) for p in rules.Priority],
    )
    prioridad_justificacion = models.TextField(_("justificación del ajuste"), blank=True)
    prioridad = models.PositiveSmallIntegerField(
        _("prioridad"),
        null=True,
        editable=False,
        db_index=True,
        choices=[(p.value, p.label) for p in rules.Priority],
    )

    # Control
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
        editable=False,
        verbose_name=_("registrado por"),
    )
    created_at = models.DateTimeField(_("fecha de registro"), auto_now_add=True)
    updated_at = models.DateTimeField(_("última actualización"), auto_now=True)

    history = HistoricalRecords(excluded_fields=["updated_at"])

    class Meta(TenantScopedModel.Meta):
        verbose_name = _("impacto")
        verbose_name_plural = _("impactos")
        ordering = ["prioridad", "numero"]
        constraints = [
            models.UniqueConstraint(fields=["client", "numero"], name="unique_impacto_numero"),
        ]

    def __str__(self):
        return f"{self.codigo} {self.titulo}"

    @property
    def codigo(self):
        return f"IMP-{self.numero:03d}" if self.numero else "IMP-nuevo"

    @property
    def tiene_criterio_cierre(self):
        return bool(self.criterio_evidencia_id and self.criterio_descripcion)

    @property
    def alerta_severidad(self):
        return self.severidad is not None and rules.is_severity_alert(self.severidad)

    @property
    def alerta_p1_sin_criterio(self):
        return self.prioridad == rules.Priority.P1 and not self.tiene_criterio_cierre

    @property
    def is_locked(self):
        """Closed or discarded impacts must be reopened before editing."""
        return self.estado in (Estado.CERRADO, Estado.DESCARTADO)

    def recalculate(self):
        if self.probabilidad and self.severidad:
            self.riesgo_puntaje = rules.risk_score(self.probabilidad, self.severidad)
            self.riesgo_nivel = rules.risk_band(self.riesgo_puntaje)
        else:
            self.riesgo_puntaje = self.riesgo_nivel = None
        if self.magnitud and self.riesgo_nivel:
            self.prioridad_calculada = rules.priority(self.magnitud, self.riesgo_nivel)
        else:
            self.prioridad_calculada = None
        self.prioridad = self.prioridad_ajustada or self.prioridad_calculada

    def save(self, *args, **kwargs):
        self.recalculate()
        with transaction.atomic():
            assign_next_number(self)
            super().save(*args, **kwargs)


class Transicion(TenantScopedModel):
    """One row per state change: who, when, why. Feeds time-based indicators."""

    impacto = models.ForeignKey(Impacto, on_delete=models.CASCADE, related_name="transiciones")
    desde = models.CharField(max_length=20, choices=Estado.choices)
    hacia = models.CharField(max_length=20, choices=Estado.choices)
    motivo = models.TextField(_("motivo"), blank=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta(TenantScopedModel.Meta):
        ordering = ["fecha"]


class Comentario(TenantScopedModel):
    impacto = models.ForeignKey(Impacto, on_delete=models.CASCADE, related_name="comentarios")
    autor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    texto = models.TextField(_("comentario"))
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta(TenantScopedModel.Meta):
        ordering = ["fecha"]


class Adjunto(AbstractAdjunto):
    UPLOAD_DIR = "impactos"

    impacto = models.ForeignKey(Impacto, on_delete=models.CASCADE, related_name="adjuntos")

    class Meta(AbstractAdjunto.Meta):
        pass


class Foto(TenantScopedModel):
    """Snapshot of the whole matrix when a stage (tiempo) closes (§1.7)."""

    tiempo = SystemCatalogField(SystemCatalog.TIEMPO, verbose_name=_("etapa que se cierra"))
    nota = models.CharField(_("nota"), max_length=300, blank=True)
    datos = models.JSONField(editable=False)
    creada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta(TenantScopedModel.Meta):
        ordering = ["-fecha"]
        verbose_name = _("foto de la matriz")
        verbose_name_plural = _("fotos de la matriz")


# States in which an impact still blocks the impacts that depend on it.
OPEN_STATES = (Estado.PROPUESTO, Estado.EVALUADO, Estado.EN_ATENCION, Estado.REABIERTO)


class Dependencia(TenantScopedModel):
    """`impacto` depende de `depende_de`. Informative only: never blocks the lifecycle."""

    impacto = models.ForeignKey(Impacto, on_delete=models.CASCADE, related_name="dependencias")
    depende_de = models.ForeignKey(
        Impacto, on_delete=models.CASCADE, related_name="dependientes", verbose_name=_("depende de")
    )
    creada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    fecha = models.DateTimeField(auto_now_add=True)

    history = HistoricalRecords()

    class Meta(TenantScopedModel.Meta):
        verbose_name = _("dependencia")
        verbose_name_plural = _("dependencias")
        ordering = ["depende_de__numero"]
        constraints = [
            models.UniqueConstraint(fields=["impacto", "depende_de"], name="unique_dependencia"),
            models.CheckConstraint(
                condition=~models.Q(impacto=models.F("depende_de")), name="dependencia_no_self"
            ),
        ]

    def __str__(self):
        return f"{self.impacto.codigo} → {self.depende_de.codigo}"
