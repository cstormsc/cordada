"""Files and links attached to client records. Files are only served through
views that check permissions (see file_response)."""

import os
import uuid

from django import forms
from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models
from django.http import FileResponse, Http404
from django.utils.translation import gettext_lazy as _

from .tenancy import TenantScopedModel

ALLOWED_EXTENSIONS = ["pdf", "docx", "xlsx", "pptx", "csv", "txt", "png", "jpg", "jpeg"]
MAX_UPLOAD_MB = 10


def attachment_path(instance, filename):
    ext = os.path.splitext(filename)[1].lower()
    return f"clientes/{instance.client_id}/{instance.UPLOAD_DIR}/{uuid.uuid4().hex}{ext}"


class AbstractAdjunto(TenantScopedModel):
    UPLOAD_DIR = "adjuntos"

    archivo = models.FileField(
        _("archivo"), upload_to=attachment_path, blank=True,
        validators=[FileExtensionValidator(ALLOWED_EXTENSIONS)],
    )
    nombre = models.CharField(_("nombre"), max_length=200, blank=True)
    url = models.URLField(_("enlace"), blank=True)
    subido_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                   related_name="+")
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta(TenantScopedModel.Meta):
        abstract = True
        ordering = ["fecha"]
        constraints = [
            models.CheckConstraint(
                condition=(~models.Q(archivo="") & models.Q(url=""))
                | (models.Q(archivo="") & ~models.Q(url="")),
                name="%(app_label)s_%(class)s_archivo_xor_url",
            ),
        ]

    def __str__(self):
        return self.nombre or self.url


class AdjuntoForm(forms.ModelForm):
    """Subclass with Meta.model set to a concrete AbstractAdjunto."""

    url = forms.URLField(label=_("Enlace"), required=False, assume_scheme="https")

    class Meta:
        fields = ["archivo", "url", "nombre"]
        help_texts = {
            "archivo": _("PDF, Office, imagen, CSV o texto. Máximo %(mb)s MB.")
            % {"mb": MAX_UPLOAD_MB},
            "nombre": _("Opcional. Por defecto, el nombre del archivo o el enlace."),
        }

    def clean_archivo(self):
        archivo = self.cleaned_data.get("archivo")
        if archivo and archivo.size > MAX_UPLOAD_MB * 1024 * 1024:
            raise forms.ValidationError(_("El archivo supera %(mb)s MB.") % {"mb": MAX_UPLOAD_MB})
        return archivo

    def clean(self):
        cleaned = super().clean()
        archivo, url = cleaned.get("archivo"), cleaned.get("url")
        if bool(archivo) == bool(url):
            raise forms.ValidationError(_("Sube un archivo o pega un enlace (uno de los dos)."))
        if not cleaned.get("nombre"):
            cleaned["nombre"] = archivo.name if archivo else url
        return cleaned

    def save_for(self, user, **owner):
        adjunto = self.save(commit=False)
        for field, value in owner.items():
            setattr(adjunto, field, value)
        adjunto.subido_por = user
        adjunto.nombre = self.cleaned_data["nombre"]
        adjunto.save()
        return adjunto


def file_response(adjunto):
    if not adjunto.archivo:
        raise Http404  # links are shown directly on the page
    return FileResponse(adjunto.archivo.open("rb"), as_attachment=True,
                        filename=adjunto.nombre or adjunto.archivo.name)
