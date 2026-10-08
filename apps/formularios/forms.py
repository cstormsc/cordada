from decimal import Decimal, InvalidOperation

from django import forms
from django.utils.translation import gettext_lazy as _

from apps.catalogs.models import GrupoImpactado
from apps.core.attachments import AdjuntoForm
from apps.matriz.models import Estado, Impacto

from .importer import GROUP_SOURCES
from .models import (
    MAX_OPTIONS,
    Acta,
    Criterio,
    Cuestionario,
    ListaObservacion,
    Opcion,
    Pregunta,
    TipoPregunta,
)

GROUP_SOURCE_CHOICES = [("", _("Ninguna"))] + [(f, _(f.capitalize())) for f in GROUP_SOURCES]


class CargaForm(forms.Form):
    archivo = forms.FileField(
        label=_("Archivo CSV o Excel"),
        help_text=_(
            "Columnas: correo (obligatoria), nombre, oficina, "
            "sucursal, departamento, supervisor y cargo."
        ),
    )
    columna_grupo = forms.ChoiceField(
        label=_("Columna que define el grupo impactado"),
        choices=GROUP_SOURCE_CHOICES,
        required=False,
        initial="departamento",
        help_text=_("Sus valores se asignan a los grupos impactados con el mismo nombre."),
    )
    crear_grupos = forms.BooleanField(
        label=_("Crear los grupos que no existan"),
        required=False,
    )


class ImpactoChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f"{obj.codigo} · {obj.titulo}"


class CuestionarioForm(forms.ModelForm):
    impacto = ImpactoChoiceField(
        label=_("Impacto que verifica"), queryset=Impacto.unscoped.none(), required=False
    )

    class Meta:
        model = Cuestionario
        fields = ["titulo", "instrucciones", "impacto", "nota_minima", "intentos", "vence"]
        widgets = {
            "instrucciones": forms.Textarea(attrs={"rows": 3}),
            "vence": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["impacto"].queryset = Impacto.objects.exclude(
            estado=Estado.DESCARTADO
        ).order_by("numero")
        if self.instance.pk and not self.instance.is_draft:
            # Once published, only the closing date can change.
            for name in ("titulo", "instrucciones", "impacto", "nota_minima", "intentos"):
                self.fields[name].disabled = True


class PreguntaForm(forms.ModelForm):
    class Meta:
        model = Pregunta
        fields = ["texto", "tipo"]
        widgets = {"texto": forms.Textarea(attrs={"rows": 2})}


class OpcionForm(forms.ModelForm):
    class Meta:
        model = Opcion
        fields = ["texto", "correcta"]


OpcionFormSet = forms.inlineformset_factory(
    Pregunta,
    Opcion,
    form=OpcionForm,
    extra=MAX_OPTIONS,
    max_num=MAX_OPTIONS,
    validate_max=True,
    can_delete=True,
)


def opcion_formset(pregunta, data=None):
    existing = pregunta.opciones.count() if pregunta.pk else 0
    formset = OpcionFormSet(
        data,
        instance=pregunta,
        prefix="op",
        queryset=pregunta.opciones.all() if pregunta.pk else Opcion.unscoped.none(),
    )
    formset.extra = MAX_OPTIONS - existing
    return formset


def parse_points(data, preguntas):
    """{pregunta: Decimal} from POST fields puntos-<id>, or raises ValueError(message)."""
    result = {}
    for n, p in enumerate(preguntas, start=1):
        raw = (data.get(f"puntos-{p.pk}") or "").replace(",", ".").strip()
        try:
            value = Decimal(raw).quantize(Decimal("0.01"))
        except (InvalidOperation, ValueError):
            raise ValueError(_("Puntos no válidos en la pregunta %(n)s.") % {"n": n}) from None
        if not Decimal("0") <= value <= Decimal("100"):
            raise ValueError(_("Cada pregunta vale entre 0 y 100 puntos."))
        result[p] = value
    return result


class EnlacesForm(forms.Form):
    grupos = forms.ModelMultipleChoiceField(
        label=_("Grupos"),
        queryset=GrupoImpactado.unscoped.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text=_("Vacío: todas las personas activas."),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["grupos"].queryset = GrupoImpactado.objects.filter(is_active=True)


DIMENSIONS = [
    ("grupo", _("Grupo impactado")),
    ("departamento", _("Departamento")),
    ("oficina", _("Oficina")),
    ("sucursal", _("Sucursal")),
    ("cargo", _("Cargo")),
]


class ResultadosForm(forms.Form):
    por = forms.ChoiceField(label=_("Agrupar por"), choices=DIMENSIONS, required=False)


TIPO_HELP = {
    TipoPregunta.SIMPLE: _("Una sola respuesta correcta."),
    TipoPregunta.SI_NO: _("Opciones Sí y No; marca la correcta."),
    TipoPregunta.MULTIPLE: _(
        "Hasta 5 opciones; puntaje completo solo si marca todas las correctas y ninguna incorrecta."
    ),
}


class ListaForm(forms.ModelForm):
    class Meta:
        model = ListaObservacion
        fields = ["titulo", "instrucciones"]
        widgets = {"instrucciones": forms.Textarea(attrs={"rows": 3})}


class CriterioForm(forms.ModelForm):
    class Meta:
        model = Criterio
        fields = ["texto"]


class ActaForm(AdjuntoForm):
    """Signed summary: a file (PDF or photo), not a link."""

    url = None  # drop the link field inherited from AdjuntoForm

    class Meta(AdjuntoForm.Meta):
        model = Acta
        fields = ["archivo"]
        help_texts = {"archivo": _("El resumen firmado: PDF escaneado o foto.")}

    def clean(self):
        cleaned = forms.ModelForm.clean(self)
        archivo = cleaned.get("archivo")
        if not archivo:
            raise forms.ValidationError(_("Sube el resumen firmado."))
        ext = archivo.name.rsplit(".", 1)[-1].lower()
        if ext not in {"pdf", "jpg", "jpeg", "png"}:
            raise forms.ValidationError(_("Sube un PDF o una imagen (JPG o PNG)."))
        cleaned["nombre"] = archivo.name
        return cleaned
