import os
import uuid

from django.core.validators import FileExtensionValidator
from django.db import models
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords

from apps.core.attachments import ALLOWED_EXTENSIONS, AbstractAdjunto

from . import anchors

# --- Methodology material: the same for every client, maintained by platform admins ---


class Tema(models.Model):
    """A methodology topic (fronts, times, decision rule...), shown on the guide page."""

    slug = models.SlugField(
        _("identificador"),
        max_length=60,
        unique=True,
        help_text=_("Ancla del tema en la guía: /guia/#tema-<identificador>."),
    )
    titulo = models.CharField(_("título"), max_length=200)
    contenido = models.TextField(
        _("contenido"),
        help_text=_("Texto plano. Los saltos de línea y los enlaces se respetan."),
    )
    orden = models.PositiveSmallIntegerField(_("orden"), default=0)
    is_active = models.BooleanField(_("activo"), default=True)

    history = HistoricalRecords()

    class Meta:
        verbose_name = _("tema de la guía")
        verbose_name_plural = _("temas de la guía")
        ordering = ["orden", "titulo"]

    def __str__(self):
        return self.titulo

    @property
    def anchor(self):
        return anchors.tema(self.slug)


def plantilla_path(instance, filename):
    ext = os.path.splitext(filename)[1].lower()
    return f"guia/plantillas/{uuid.uuid4().hex}{ext}"


class Plantilla(models.Model):
    """A template file or link offered to every client."""

    nombre = models.CharField(_("nombre"), max_length=200)
    descripcion = models.TextField(_("descripción"), blank=True)
    archivo = models.FileField(
        _("archivo"),
        upload_to=plantilla_path,
        blank=True,
        validators=[FileExtensionValidator(ALLOWED_EXTENSIONS)],
    )
    url = models.URLField(_("enlace"), blank=True)
    orden = models.PositiveSmallIntegerField(_("orden"), default=0)
    is_active = models.BooleanField(_("activa"), default=True)

    history = HistoricalRecords()

    class Meta:
        verbose_name = _("plantilla")
        verbose_name_plural = _("plantillas")
        ordering = ["orden", "nombre"]
        constraints = [
            models.CheckConstraint(
                condition=(~models.Q(archivo="") & models.Q(url=""))
                | (models.Q(archivo="") & ~models.Q(url="")),
                name="guia_plantilla_archivo_xor_url",
            ),
        ]

    def __str__(self):
        return self.nombre


# --- Client documents: each client keeps its own ---


class Documento(AbstractAdjunto):
    UPLOAD_DIR = "guia"

    descripcion = models.CharField(_("descripción"), max_length=300, blank=True)

    class Meta(AbstractAdjunto.Meta):
        verbose_name = _("documento del cliente")
        verbose_name_plural = _("documentos del cliente")
        ordering = ["nombre"]
