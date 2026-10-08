from django import forms

from apps.core.attachments import AdjuntoForm

from .models import Documento, Plantilla, Tema


class TemaForm(forms.ModelForm):
    class Meta:
        model = Tema
        fields = ["titulo", "slug", "contenido", "orden", "is_active"]
        widgets = {"contenido": forms.Textarea(attrs={"rows": 14})}


class PlantillaForm(AdjuntoForm):
    """Same file rules as attachments: a file or a link, size-limited."""

    class Meta(AdjuntoForm.Meta):
        model = Plantilla
        fields = ["nombre", "descripcion", "archivo", "url", "orden", "is_active"]
        widgets = {"descripcion": forms.Textarea(attrs={"rows": 3})}


class DocumentoForm(AdjuntoForm):
    class Meta(AdjuntoForm.Meta):
        model = Documento
        fields = ["archivo", "url", "nombre", "descripcion"]
