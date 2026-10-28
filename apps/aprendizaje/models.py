from datetime import timedelta

from django.conf import settings
from django.core import signing
from django.core.validators import FileExtensionValidator
from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords

from apps.core.attachments import ALLOWED_EXTENSIONS, attachment_path
from apps.core.tenancy import TenantScopedModel, assign_next_number
from apps.formularios.models import Cuestionario, Persona
from apps.matriz.models import Impacto


class EstadoCurso(models.TextChoices):
    BORRADOR = "borrador", _("Borrador")
    PUBLICADO = "publicado", _("Publicado")
    CERRADO = "cerrado", _("Cerrado")


class Curso(TenantScopedModel):
    """Lessons that prepare people for one or more impacts, optionally ending in a
    Formularios questionnaire."""

    numero = models.PositiveIntegerField(_("ID"), editable=False)
    titulo = models.CharField(_("título"), max_length=200)
    descripcion = models.TextField(
        _("descripción"),
        blank=True,
        help_text=_("Lo que ve la persona al abrir el curso."),
    )
    impactos = models.ManyToManyField(
        Impacto,
        related_name="cursos",
        blank=True,
        verbose_name=_("impactos que prepara"),
    )
    evaluacion = models.ForeignKey(
        Cuestionario,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="cursos",
        verbose_name=_("evaluación"),
        help_text=_("Opcional. Un cuestionario de Formularios: el curso se completa al aprobarlo."),
    )
    fecha_limite = models.DateField(
        _("fecha límite"),
        null=True,
        blank=True,
        help_text=_(
            "Opcional. Quien completa el curso hasta esta fecha cuenta como formado antes "
            "de la salida."
        ),
    )
    estado = models.CharField(
        _("estado"),
        max_length=20,
        choices=EstadoCurso.choices,
        default=EstadoCurso.BORRADOR,
        editable=False,
    )
    publicado_at = models.DateTimeField(null=True, editable=False)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+", editable=False
    )
    created_at = models.DateTimeField(auto_now_add=True)

    history = HistoricalRecords()

    class Meta(TenantScopedModel.Meta):
        verbose_name = _("curso")
        verbose_name_plural = _("cursos")
        ordering = ["-numero"]
        constraints = [
            models.UniqueConstraint(fields=["client", "numero"], name="unique_curso_numero"),
        ]

    def __str__(self):
        return f"{self.codigo} {self.titulo}"

    @property
    def codigo(self):
        return f"CUR-{self.numero:03d}" if self.numero else "CUR-nuevo"

    @property
    def is_draft(self):
        return self.estado == EstadoCurso.BORRADOR

    @property
    def is_open(self):
        return self.estado == EstadoCurso.PUBLICADO

    def save(self, *args, **kwargs):
        with transaction.atomic():
            assign_next_number(self)
            super().save(*args, **kwargs)


class Leccion(TenantScopedModel):
    """A lesson is a sequence of blocks (text, image, video, steps...)."""

    curso = models.ForeignKey(Curso, on_delete=models.CASCADE, related_name="lecciones")
    orden = models.PositiveSmallIntegerField(default=0)
    titulo = models.CharField(_("título"), max_length=200)
    minutos = models.PositiveSmallIntegerField(_("minutos estimados"), null=True, blank=True)
    obligatoria = models.BooleanField(
        _("obligatoria"),
        default=True,
        help_text=_("Las obligatorias cuentan para completar un curso sin evaluación."),
    )
    depende_de = models.ManyToManyField(
        "self",
        symmetrical=False,
        related_name="habilita",
        blank=True,
        verbose_name=_("depende de"),
        help_text=_("Se abre solo cuando la persona vio estas lecciones."),
    )

    history = HistoricalRecords()

    class Meta(TenantScopedModel.Meta):
        verbose_name = _("lección")
        verbose_name_plural = _("lecciones")
        ordering = ["orden", "pk"]

    def __str__(self):
        return self.titulo


class TipoBloque(models.TextChoices):
    TEXTO = "texto", _("Texto")
    NOTA = "nota", _("Nota destacada")
    IMAGEN = "imagen", _("Imagen")
    VIDEO = "video", _("Video")
    DOCUMENTO = "documento", _("Documento")
    PASOS = "pasos", _("Paso a paso")
    ACORDEON = "acordeon", _("Acordeón")


# Blocks whose content is a list of items (steps, accordion sections).
CON_ITEMS = (TipoBloque.PASOS, TipoBloque.ACORDEON)
IMAGE_EXTENSIONS = ["png", "jpg", "jpeg", "gif", "webp"]


class Bloque(TenantScopedModel):
    UPLOAD_DIR = "lecciones"

    leccion = models.ForeignKey(Leccion, on_delete=models.CASCADE, related_name="bloques")
    orden = models.PositiveSmallIntegerField(default=0)
    tipo = models.CharField(_("tipo"), max_length=10, choices=TipoBloque.choices)
    titulo = models.CharField(
        _("título"), max_length=200, blank=True, help_text=_("Opcional. Encabezado del bloque.")
    )
    texto = models.TextField(
        _("texto"),
        blank=True,
        help_text=_("Texto plano. Los saltos de línea y los enlaces se respetan."),
    )
    url = models.URLField(_("enlace"), blank=True)
    archivo = models.FileField(
        _("archivo"),
        upload_to=attachment_path,
        blank=True,
        validators=[FileExtensionValidator(sorted({*ALLOWED_EXTENSIONS, *IMAGE_EXTENSIONS}))],
    )

    class Meta(TenantScopedModel.Meta):
        verbose_name = _("bloque")
        verbose_name_plural = _("bloques")
        ordering = ["orden", "pk"]

    def __str__(self):
        return self.titulo or self.get_tipo_display()


class BloqueItem(TenantScopedModel):
    """One step of a step-by-step block, or one section of an accordion."""

    UPLOAD_DIR = "lecciones"

    bloque = models.ForeignKey(Bloque, on_delete=models.CASCADE, related_name="items")
    orden = models.PositiveSmallIntegerField(default=0)
    titulo = models.CharField(_("título"), max_length=200, blank=True)
    texto = models.TextField(_("texto"), blank=True)
    imagen = models.FileField(
        _("imagen"),
        upload_to=attachment_path,
        blank=True,
        validators=[FileExtensionValidator(IMAGE_EXTENSIONS)],
    )

    class Meta(TenantScopedModel.Meta):
        ordering = ["orden", "pk"]

    def __str__(self):
        return self.titulo


class Inscripcion(TenantScopedModel):
    """One person in one course, reached through a personal link like Formularios' Enlace:
    the token is signed, not stored, and bumping `version` revokes old links."""

    SALT = "aprendizaje.inscripcion"

    curso = models.ForeignKey(Curso, on_delete=models.CASCADE, related_name="inscripciones")
    persona = models.ForeignKey(Persona, on_delete=models.CASCADE, related_name="inscripciones")
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    iniciada_at = models.DateTimeField(null=True, blank=True)
    directo_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("Cuándo la persona confirmó que iba directo a la evaluación."),
    )
    completada_at = models.DateTimeField(null=True, blank=True)

    class Meta(TenantScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["curso", "persona"], name="unique_inscripcion"),
        ]

    @property
    def token(self):
        return signing.dumps({"i": self.pk, "v": self.version}, salt=self.SALT, compress=True)

    @staticmethod
    def validez():
        return timedelta(days=settings.FORMULARIOS_ENLACE_DIAS)

    @classmethod
    def from_token(cls, token):
        """Returns the Inscripcion (any client) or None, with `vencido` set."""
        try:
            data = signing.loads(token, salt=cls.SALT)
        except signing.BadSignature:
            return None
        inscripcion = (
            cls.unscoped.select_related("client", "curso", "persona")
            .filter(pk=data.get("i"))
            .first()
        )
        if inscripcion is None or inscripcion.version != data.get("v"):
            return None
        try:
            signing.loads(token, salt=cls.SALT, max_age=cls.validez())
            inscripcion.vencido = False
        except signing.SignatureExpired:
            inscripcion.vencido = True
        return inscripcion


class LeccionVista(TenantScopedModel):
    inscripcion = models.ForeignKey(Inscripcion, on_delete=models.CASCADE, related_name="vistas")
    leccion = models.ForeignKey(Leccion, on_delete=models.CASCADE, related_name="vistas")
    vista_at = models.DateTimeField(default=timezone.now)

    class Meta(TenantScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["inscripcion", "leccion"], name="unique_vista"),
        ]
