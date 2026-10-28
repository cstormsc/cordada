from django import forms
from django.utils.translation import gettext_lazy as _
from PIL import Image

from apps.core.attachments import MAX_UPLOAD_MB
from apps.formularios.models import Cuestionario, EstadoCuestionario
from apps.matriz.models import Estado, Impacto

from . import cursos
from .models import (
    IMAGE_EXTENSIONS,
    Ajustes,
    Bloque,
    BloqueItem,
    Curso,
    Encabezado,
    Leccion,
    Montana,
    TipoBloque,
)


class ImpactosField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj):
        return f"{obj.codigo} · {obj.titulo}"


class CuestionarioChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f"{obj.codigo} · {obj.titulo} ({obj.get_estado_display().lower()})"


class CursoForm(forms.ModelForm):
    impactos = ImpactosField(
        label=_("Impactos que prepara"),
        queryset=Impacto.unscoped.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text=_("Los que requieren formación aparecen primero."),
    )
    evaluacion = CuestionarioChoiceField(
        label=_("Evaluación"),
        queryset=Cuestionario.unscoped.none(),
        required=False,
        help_text=Curso._meta.get_field("evaluacion").help_text,
    )

    class Meta:
        model = Curso
        fields = ["titulo", "descripcion", "impactos", "evaluacion", "fecha_limite", "montana"]
        widgets = {
            "descripcion": forms.Textarea(attrs={"rows": 3}),
            "fecha_limite": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }

    def __init__(self, *args, expedicion=True, **kwargs):
        super().__init__(*args, **kwargs)
        if expedicion:
            self.fields["montana"].required = False
        else:
            del self.fields["montana"]
        self.fields["impactos"].queryset = Impacto.objects.exclude(
            estado=Estado.DESCARTADO
        ).order_by("-requiere_formacion", "numero")
        self.fields["evaluacion"].queryset = Cuestionario.objects.exclude(
            estado=EstadoCuestionario.CERRADO
        ).order_by("numero")
        if self.instance.pk and not self.instance.is_draft:
            # Once published, people may be taking it: only the texts and the date change.
            for name in ("impactos", "evaluacion"):
                self.fields[name].disabled = True

    def clean_montana(self):
        return self.cleaned_data.get("montana") or self.instance.montana or Montana.BARU


class LeccionForm(forms.ModelForm):
    depende_de = forms.ModelMultipleChoiceField(
        label=_("Depende de"),
        queryset=Leccion.unscoped.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text=Leccion._meta.get_field("depende_de").help_text,
    )

    class Meta:
        model = Leccion
        fields = ["titulo", "minutos", "obligatoria", "depende_de"]

    def __init__(self, *args, curso, **kwargs):
        super().__init__(*args, **kwargs)
        self.curso = curso
        otras = curso.lecciones.all()
        if self.instance.pk:
            otras = otras.exclude(pk=self.instance.pk)
        self.fields["depende_de"].queryset = otras
        self.fields["depende_de"].label_from_instance = lambda o: f"{o.orden}. {o.titulo}"
        if not otras:
            del self.fields["depende_de"]
        if not curso.is_draft:
            # Published: content can be corrected; the course's structure stays.
            for name in ("obligatoria", "depende_de"):
                if name in self.fields:
                    self.fields[name].disabled = True

    def clean_depende_de(self):
        deps = self.cleaned_data.get("depende_de")
        if deps and self.instance.pk:
            graph = cursos.dependency_graph(self.curso)
            if cursos.creates_cycle(graph, self.instance.pk, {d.pk for d in deps}):
                raise forms.ValidationError(
                    _(
                        "Se formaría un ciclo: una de esas lecciones ya depende, directa o "
                        "indirectamente, de esta."
                    )
                )
        return deps


def _check_size(f):
    if f and f.size > MAX_UPLOAD_MB * 1024 * 1024:
        raise forms.ValidationError(_("El archivo supera %(mb)s MB.") % {"mb": MAX_UPLOAD_MB})
    return f


T = TipoBloque
# Fields each block type shows, and how they are labelled there.
BLOCK_FIELDS = {
    T.TEXTO: {"titulo": None, "texto": None},
    T.NOTA: {"titulo": None, "texto": None},
    T.IMAGEN: {"archivo": _("Imagen"), "titulo": None, "texto": _("Pie de imagen (opcional)")},
    T.VIDEO: {"titulo": None, "url": _("Enlace del video"), "texto": _("Texto (opcional)")},
    T.DOCUMENTO: {
        "titulo": None,
        "archivo": _("Documento"),
        "url": _("o enlace al documento"),
        "texto": _("Texto (opcional)"),
    },
    T.PASOS: {"titulo": None, "texto": _("Introducción (opcional)")},
    T.ACORDEON: {"titulo": None, "texto": _("Introducción (opcional)")},
    T.PREGUNTA: {"titulo": None, "texto": _("Pregunta")},
    T.ORDENAR: {"titulo": None, "texto": _("Instrucción (opcional)")},
}
BLOCK_HELP = {
    T.NOTA: _("Un texto resaltado: una advertencia, un dato clave, un recordatorio."),
    T.IMAGEN: _("PNG, JPG, GIF o WebP. Máximo %(mb)s MB.") % {"mb": MAX_UPLOAD_MB},
    T.VIDEO: _("YouTube y Vimeo se ven dentro de la lección; otros enlaces, como botón."),
    T.PASOS: _("Un carrusel: la persona avanza paso a paso con Anterior y Siguiente."),
    T.ACORDEON: _("Secciones que la persona abre y cierra."),
    T.PREGUNTA: _(
        "Una pregunta para repasar en medio de la lección. Si se equivoca, la persona ve la "
        "explicación y reintenta; no cuenta para la nota. Con la expedición activada se "
        "juega como «Cruzar la grieta»."
    ),
    T.ORDENAR: _(
        "Escribe los pasos en el orden correcto: la persona los verá desordenados y debe "
        "ordenarlos. No cuenta para la nota. Con la expedición activada se juega como "
        "«Arma la ruta»."
    ),
}


class BloqueForm(forms.ModelForm):
    url = forms.URLField(label=_("Enlace"), required=False, assume_scheme="https")

    class Meta:
        model = Bloque
        fields = ["titulo", "texto", "url", "archivo"]
        widgets = {"texto": forms.Textarea(attrs={"rows": 8})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        shown = BLOCK_FIELDS[self.instance.tipo]
        for name in list(self.fields):
            if name not in shown:
                del self.fields[name]
            elif shown[name]:
                self.fields[name].label = shown[name]
        if self.instance.tipo in (T.TEXTO, T.NOTA, T.PREGUNTA):
            self.fields["texto"].required = True
        if self.instance.tipo == T.VIDEO:
            self.fields["url"].required = True
        if self.instance.tipo == T.IMAGEN:
            self.fields["archivo"].widget.attrs["accept"] = "image/*"

    def clean_archivo(self):
        f = _check_size(self.cleaned_data.get("archivo"))
        if f and self.instance.tipo == T.IMAGEN:
            ext = f.name.rsplit(".", 1)[-1].lower()
            if ext not in IMAGE_EXTENSIONS:
                raise forms.ValidationError(_("Sube una imagen PNG, JPG, GIF o WebP."))
        return f


# Fields each item shows by block type, and how they are labelled there.
ITEM_FIELDS = {
    T.PREGUNTA: {
        "titulo": _("Opción"),
        "texto": _("Explicación (se muestra al elegirla)"),
        "correcta": None,
    },
    T.ORDENAR: {"titulo": _("Paso")},
}


class BloqueItemForm(forms.ModelForm):
    class Meta:
        model = BloqueItem
        fields = ["titulo", "texto", "imagen", "correcta"]
        widgets = {
            "texto": forms.Textarea(attrs={"rows": 3}),
            "imagen": forms.ClearableFileInput(attrs={"accept": "image/*"}),
        }

    def __init__(self, *args, tipo, **kwargs):
        super().__init__(*args, **kwargs)
        shown = ITEM_FIELDS.get(tipo, {"titulo": None, "texto": None, "imagen": None})
        for name in ("titulo", "texto", "imagen", "correcta"):
            if name not in shown:
                del self.fields[name]
            elif shown[name]:
                self.fields[name].label = shown[name]

    def clean_imagen(self):
        return _check_size(self.cleaned_data.get("imagen"))


MAX_ITEMS = 12
ItemFormSet = forms.inlineformset_factory(
    Bloque,
    BloqueItem,
    form=BloqueItemForm,
    extra=0,
    max_num=MAX_ITEMS,
    validate_max=True,
    can_delete=True,
)


def item_formset(bloque, data=None, files=None):
    existing = bloque.items.count() if bloque.pk else 0
    formset = ItemFormSet(
        data,
        files,
        instance=bloque,
        prefix="it",
        queryset=bloque.items.all() if bloque.pk else BloqueItem.unscoped.none(),
        form_kwargs={"tipo": bloque.tipo},
    )
    formset.extra = min(MAX_ITEMS - existing, max(2, 4 - existing))
    return formset


def kept_items(formset):
    """The (form, titulo, texto, correcta) the formset keeps: not deleted and not left
    empty."""
    kept = []
    for form in formset.forms:
        data = getattr(form, "cleaned_data", None) or {}
        if not data or data.get("DELETE"):
            continue
        titulo, texto = data.get("titulo", ""), data.get("texto", "")
        if titulo or texto or data.get("imagen"):
            kept.append((form, titulo, texto, bool(data.get("correcta"))))
    return kept


class EncabezadoForm(forms.ModelForm):
    class Meta:
        model = Encabezado
        fields = ["imagen", "texto_alternativo"]
        widgets = {"imagen": forms.FileInput(attrs={"accept": "image/png,image/jpeg,image/webp"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.dimensiones = None
        self.fields["imagen"].help_text = _(
            "Recomendado: %(w)s × %(h)s px (proporción 6:1), PNG o JPG, hasta %(mb)s MB. Se "
            "muestra completa a todo el ancho de la página; en el celular se ve más pequeña, "
            "así que evita letras chicas y deja el logo lejos de los bordes."
        ) % {"w": Encabezado.ANCHO, "h": Encabezado.ALTO, "mb": MAX_UPLOAD_MB}

    def clean_imagen(self):
        f = _check_size(self.cleaned_data.get("imagen"))
        if f and f is not getattr(self.instance, "imagen", None):
            try:
                with Image.open(f) as img:
                    self.dimensiones = img.size
            except (OSError, Image.DecompressionBombError):
                raise forms.ValidationError(_("No se pudo leer la imagen.")) from None
            f.seek(0)
        return f


class AjustesForm(forms.ModelForm):
    class Meta:
        model = Ajustes
        fields = ["expedicion"]
