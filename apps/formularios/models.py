from decimal import Decimal

from django.conf import settings
from django.core import signing
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords

from apps.catalogs.models import GrupoImpactado
from apps.core.attachments import AbstractAdjunto
from apps.core.tenancy import TenantScopedModel, assign_next_number
from apps.matriz.models import Impacto

TOTAL_POINTS = Decimal("100.00")
MAX_OPTIONS = 5


class Persona(TenantScopedModel):
    """Someone who answers questionnaires. No account: they use a personal link (§7.1)."""

    email = models.EmailField(_("correo"))
    nombre = models.CharField(_("nombre"), max_length=200, blank=True)
    oficina = models.CharField(_("oficina"), max_length=150, blank=True)
    sucursal = models.CharField(_("sucursal"), max_length=150, blank=True)
    departamento = models.CharField(_("departamento"), max_length=150, blank=True)
    supervisor = models.CharField(_("supervisor"), max_length=200, blank=True,
                                  help_text=_("Correo del líder directo."))
    cargo = models.CharField(_("cargo"), max_length=150, blank=True)
    grupo = models.ForeignKey(GrupoImpactado, on_delete=models.SET_NULL, null=True, blank=True,
                              related_name="personas_cargadas",
                              verbose_name=_("grupo impactado"))
    is_active = models.BooleanField(_("activa"), default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    history = HistoricalRecords(excluded_fields=["updated_at"])

    class Meta(TenantScopedModel.Meta):
        verbose_name = _("persona")
        verbose_name_plural = _("personas")
        ordering = ["nombre", "email"]
        constraints = [
            models.UniqueConstraint("client", models.functions.Lower("email"),
                                    name="unique_persona_email"),
        ]

    def __str__(self):
        return self.nombre or self.email

    def save(self, *args, **kwargs):
        self.email = self.email.strip().lower()
        self.supervisor = self.supervisor.strip().lower()
        super().save(*args, **kwargs)


class Carga(TenantScopedModel):
    """One upload of the people list, with its outcome."""

    archivo = models.CharField(_("archivo"), max_length=255)
    columna_grupo = models.CharField(_("columna asignada al grupo"), max_length=100, blank=True)
    filas = models.PositiveIntegerField(default=0)
    creadas = models.PositiveIntegerField(default=0)
    actualizadas = models.PositiveIntegerField(default=0)
    errores = models.JSONField(default=list)
    creada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                   related_name="+")
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta(TenantScopedModel.Meta):
        ordering = ["-fecha"]


class EstadoCuestionario(models.TextChoices):
    BORRADOR = "borrador", _("Borrador")
    PUBLICADO = "publicado", _("Publicado")
    CERRADO = "cerrado", _("Cerrado")


class Cuestionario(TenantScopedModel):
    numero = models.PositiveIntegerField(_("ID"), editable=False)
    titulo = models.CharField(_("título"), max_length=200)
    instrucciones = models.TextField(
        _("instrucciones"), blank=True,
        help_text=_("Lo que ve la persona antes de responder."),
    )
    impacto = models.ForeignKey(Impacto, on_delete=models.PROTECT, null=True, blank=True,
                                related_name="cuestionarios",
                                verbose_name=_("impacto que verifica"))
    nota_minima = models.DecimalField(
        _("nota mínima para aprobar"), max_digits=5, decimal_places=2, default=Decimal("80"),
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text=_("Sobre 100 puntos."),
    )
    intentos = models.PositiveSmallIntegerField(
        _("intentos permitidos"), default=1, validators=[MinValueValidator(1)],
    )
    vence = models.DateField(_("vence"), null=True, blank=True,
                             help_text=_("Opcional. Después de esta fecha los enlaces no "
                                         "aceptan respuestas."))
    puntos_manuales = models.BooleanField(default=False, editable=False)
    estado = models.CharField(_("estado"), max_length=20, choices=EstadoCuestionario.choices,
                              default=EstadoCuestionario.BORRADOR, editable=False)
    publicado_at = models.DateTimeField(null=True, editable=False)
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                   related_name="+", editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    history = HistoricalRecords()

    class Meta(TenantScopedModel.Meta):
        verbose_name = _("cuestionario")
        verbose_name_plural = _("cuestionarios")
        ordering = ["-numero"]
        constraints = [
            models.UniqueConstraint(fields=["client", "numero"],
                                    name="unique_cuestionario_numero"),
        ]

    def __str__(self):
        return f"{self.codigo} {self.titulo}"

    @property
    def codigo(self):
        return f"CUE-{self.numero:03d}" if self.numero else "CUE-nuevo"

    @property
    def is_draft(self):
        return self.estado == EstadoCuestionario.BORRADOR

    @property
    def is_open(self):
        return (self.estado == EstadoCuestionario.PUBLICADO
                and (self.vence is None or self.vence >= timezone.localdate()))

    def total_puntos(self):
        return sum((p.puntos for p in self.preguntas.all()), Decimal("0"))

    def save(self, *args, **kwargs):
        with transaction.atomic():
            assign_next_number(self)
            super().save(*args, **kwargs)


class TipoPregunta(models.TextChoices):
    SIMPLE = "simple", _("Selección simple")
    SI_NO = "si_no", _("Sí o no")
    MULTIPLE = "multiple", _("Opción múltiple")


class Pregunta(TenantScopedModel):
    cuestionario = models.ForeignKey(Cuestionario, on_delete=models.CASCADE,
                                     related_name="preguntas")
    orden = models.PositiveSmallIntegerField(default=0)
    texto = models.TextField(_("pregunta"))
    tipo = models.CharField(_("tipo"), max_length=10, choices=TipoPregunta.choices,
                            default=TipoPregunta.SIMPLE)
    puntos = models.DecimalField(_("puntos"), max_digits=5, decimal_places=2,
                                 default=Decimal("0"),
                                 validators=[MinValueValidator(0), MaxValueValidator(100)])

    class Meta(TenantScopedModel.Meta):
        ordering = ["orden", "pk"]

    def __str__(self):
        return self.texto


class Opcion(TenantScopedModel):
    pregunta = models.ForeignKey(Pregunta, on_delete=models.CASCADE, related_name="opciones")
    orden = models.PositiveSmallIntegerField(default=0)
    texto = models.CharField(_("opción"), max_length=300)
    correcta = models.BooleanField(_("correcta"), default=False)

    class Meta(TenantScopedModel.Meta):
        ordering = ["orden", "pk"]

    def __str__(self):
        return self.texto


class Enlace(TenantScopedModel):
    """One personal link per person and questionnaire (§7.3). The token is signed, not
    stored, so the list can be exported again; bumping `version` revokes old links."""

    SALT = "formularios.enlace"

    cuestionario = models.ForeignKey(Cuestionario, on_delete=models.CASCADE,
                                     related_name="enlaces")
    persona = models.ForeignKey(Persona, on_delete=models.CASCADE, related_name="enlaces")
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["cuestionario", "persona"], name="unique_enlace"),
        ]

    @property
    def token(self):
        return signing.dumps({"e": self.pk, "v": self.version}, salt=self.SALT, compress=True)

    @classmethod
    def from_token(cls, token):
        """Returns the Enlace (any client) or None. Callers set the client context."""
        try:
            data = signing.loads(token, salt=cls.SALT)
        except signing.BadSignature:
            return None
        enlace = cls.unscoped.select_related("client", "cuestionario", "persona").filter(
            pk=data.get("e")).first()
        if enlace is None or enlace.version != data.get("v"):
            return None
        return enlace

    def intentos_usados(self):
        return self.respuestas.count()


class Respuesta(TenantScopedModel):
    """One attempt. Confidential, not anonymous (§7.4)."""

    enlace = models.ForeignKey(Enlace, on_delete=models.CASCADE, related_name="respuestas")
    intento = models.PositiveSmallIntegerField()
    elecciones = models.JSONField()  # {pregunta_id: [opcion_id, ...]}
    puntos_por_pregunta = models.JSONField()  # {pregunta_id: "33.33"}
    puntaje = models.DecimalField(max_digits=5, decimal_places=2)
    aprobado = models.BooleanField()
    enviada_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantScopedModel.Meta):
        ordering = ["enviada_at"]
        constraints = [
            models.UniqueConstraint(fields=["enlace", "intento"], name="unique_intento"),
        ]


# --- Leader's practical evaluation (§7.5) ---


class EstadoLista(models.TextChoices):
    BORRADOR = "borrador", _("Borrador")
    PUBLICADA = "publicada", _("Publicada")


class ListaObservacion(TenantScopedModel):
    """Observation checklist for one impact. Each criterion: cumple / no cumple."""

    impacto = models.OneToOneField(Impacto, on_delete=models.PROTECT,
                                   related_name="lista_observacion",
                                   verbose_name=_("impacto"))
    titulo = models.CharField(_("título"), max_length=200)
    instrucciones = models.TextField(_("instrucciones para el líder"), blank=True)
    estado = models.CharField(max_length=20, choices=EstadoLista.choices,
                              default=EstadoLista.BORRADOR, editable=False)
    creada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                   related_name="+", editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    history = HistoricalRecords()

    class Meta(TenantScopedModel.Meta):
        verbose_name = _("lista de observación")
        verbose_name_plural = _("listas de observación")
        ordering = ["impacto__numero"]

    def __str__(self):
        return self.titulo

    @property
    def is_draft(self):
        return self.estado == EstadoLista.BORRADOR


class Criterio(TenantScopedModel):
    lista = models.ForeignKey(ListaObservacion, on_delete=models.CASCADE,
                              related_name="criterios")
    orden = models.PositiveSmallIntegerField(default=0)
    texto = models.CharField(_("criterio"), max_length=300,
                             help_text=_("Una conducta observable: qué debe hacer bien."))

    class Meta(TenantScopedModel.Meta):
        ordering = ["orden", "pk"]

    def __str__(self):
        return self.texto


class EstadoCertificacion(models.TextChoices):
    PENDIENTE = "pendiente", _("Pendiente")
    APLICADO = "aplicado", _("Aplicado")
    CERTIFICADO = "certificado", _("Certificado")
    EN_REFUERZO = "en_refuerzo", _("En refuerzo")


class Evaluacion(TenantScopedModel):
    """One person's practical evaluation by their leader."""

    lista = models.ForeignKey(ListaObservacion, on_delete=models.CASCADE,
                              related_name="evaluaciones")
    persona = models.ForeignKey(Persona, on_delete=models.CASCADE, related_name="evaluaciones")
    lider = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                              related_name="+")
    resultados = models.JSONField(default=dict)  # {criterio_id: true/false}
    observaciones = models.TextField(_("observaciones"), blank=True)
    estado = models.CharField(max_length=20, choices=EstadoCertificacion.choices,
                              default=EstadoCertificacion.PENDIENTE)
    aplicada_at = models.DateTimeField(null=True, blank=True)
    acta = models.ForeignKey("Acta", on_delete=models.SET_NULL, null=True, blank=True,
                             related_name="evaluaciones")

    history = HistoricalRecords()

    class Meta(TenantScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["lista", "persona"], name="unique_evaluacion"),
        ]

    def cumple_todo(self, criterio_ids):
        return all(self.resultados.get(str(cid)) is True for cid in criterio_ids)


class Acta(AbstractAdjunto):
    """The signed summary the leader uploads: evidence for the impact (§7.5)."""

    UPLOAD_DIR = "actas"

    lista = models.ForeignKey(ListaObservacion, on_delete=models.CASCADE, related_name="actas")
    lider = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                              related_name="+")

    class Meta(AbstractAdjunto.Meta):
        ordering = ["-fecha"]
