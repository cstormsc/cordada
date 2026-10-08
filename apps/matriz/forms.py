import json

from django import forms
from django.utils.translation import gettext_lazy as _

from apps.catalogs.models import CategoriaResponsable, GrupoImpactado, Scale
from apps.core.attachments import AdjuntoForm as BaseAdjuntoForm
from apps.core.models import User
from apps.scoring import rules

from .models import (
    ACTIVE_STATES,
    OPEN_STATES,
    Adjunto,
    Comentario,
    Estado,
    Foto,
    Impacto,
    sin_criterio_q,
)


class ScaleSelect(forms.Select):
    """Select that shows the chosen level's written definition below it."""

    template_name = "matriz/widgets/scale_select.html"

    def __init__(self, definitions=None, attrs=None):
        super().__init__(attrs={"x-on:change": "val = $event.target.value", **(attrs or {})})
        self.definitions = definitions or {}

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        context["widget"]["definitions_json"] = json.dumps(self.definitions)
        context["widget"]["initial"] = "" if value is None else str(value)
        return context


class YesNoSelect(forms.NullBooleanSelect):
    def __init__(self, attrs=None):
        super().__init__(attrs)
        self.choices = [("unknown", _("Sin definir")), ("true", _("Sí")), ("false", _("No"))]


class MemberChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return obj.display_name


SCALE_FIELDS = {
    "magnitud": "magnitud",
    "resistencia": "resistencia",
    "preparacion": "preparacion",
    "probabilidad": "probabilidad",
    "severidad": "severidad",
}


def active_or_current(queryset, current_id):
    """Active items, plus the current value even if it was deactivated since."""
    from django.db.models import Q

    return queryset.filter(Q(is_active=True) | Q(pk=current_id))


class BaseImpactoForm(forms.ModelForm):
    # Tenant-scoped choices are declared here and filled in __init__, because the
    # generated fields would query before any client is active.
    grupo = forms.ModelChoiceField(
        label=_("Grupo impactado"), queryset=GrupoImpactado.unscoped.none(), required=False,
    )

    sections: list[tuple[str, list[str]]] = []

    def __init__(self, *args, client, **kwargs):
        super().__init__(*args, **kwargs)
        self.client = client
        self.fields["grupo"].queryset = active_or_current(
            GrupoImpactado.objects.all(), self.instance.grupo_id
        )
        self.pending_scales = []
        scales = {s.code: s for s in Scale.objects.prefetch_related("levels")}
        for name, code in SCALE_FIELDS.items():
            if name not in self.fields:
                continue
            scale = scales.get(code)
            if scale is None or not scale.is_defined:
                del self.fields[name]
                self.pending_scales.append(Impacto._meta.get_field(name).verbose_name)
                continue
            levels = list(scale.levels.all())
            field = self.fields[name]
            field.widget = ScaleSelect(definitions={str(lv.value): lv.definition for lv in levels})
            field.widget.choices = [("", "—"), *scale.choices()]
            if scale.help_text and not field.help_text:
                field.help_text = scale.help_text
        for field in self.fields.values():
            if isinstance(field, forms.NullBooleanField):
                field.widget = YesNoSelect()

    def get_sections(self):
        """[(title, [bound fields])] with only the fields present in this form."""
        return [
            (title, [self[name] for name in names if name in self.fields])
            for title, names in self.sections
        ]


class ProposalForm(BaseImpactoForm):
    """What captains, guides and the technical team fill in to propose an impact."""

    class Meta:
        model = Impacto
        fields = [
            "titulo", "descripcion", "situacion_actual", "situacion_futura", "origen",
            "tipo", "tiempo", "grupo", "grupo_sugerido", "personas_impactadas",
        ]

    sections = [
        (_("Identificación"), ["titulo", "descripcion", "situacion_actual", "situacion_futura",
                               "origen"]),
        (_("Clasificación"), ["tipo", "tiempo"]),
        (_("Quién"), ["grupo", "grupo_sugerido", "personas_impactadas"]),
    ]

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("grupo"):
            cleaned["grupo_sugerido"] = ""
        return cleaned


IMPACTO_SECTIONS = [
    (_("Identificación"), ["titulo", "descripcion", "situacion_actual", "situacion_futura",
                           "origen"]),
    (_("Clasificación"), ["tipo", "tiempo"]),
    (_("Quién"), ["grupo", "personas_impactadas"]),
    (_("Evaluación"), ["magnitud", "resistencia", "preparacion"]),
    (_("Riesgo"), ["riesgo_descripcion", "probabilidad", "severidad"]),
    (_("Derivación"), ["requiere_comunicacion", "requiere_movilizacion", "requiere_formacion",
                       "tipo_cambio_conocimiento", "formacion_criticidad", "formacion_momento"]),
    (_("Mitigación y acción"), ["medida", "responsable", "responsable_categoria",
                                "fecha_compromiso"]),
    (_("Criterio de cierre"), ["criterio_evidencia", "criterio_meta", "criterio_descripcion",
                               "requiere_certificacion_lider"]),
]


class ImpactoForm(BaseImpactoForm):
    """Full form, for roles that edit the matrix."""

    responsable = MemberChoiceField(label=_("Responsable"), queryset=User.objects.none(),
                                    required=False)
    responsable_categoria = forms.ModelChoiceField(
        label=_("Categoría del responsable"), queryset=CategoriaResponsable.unscoped.none(),
        required=False,
    )

    class Meta:
        model = Impacto
        fields = [name for _title, names in IMPACTO_SECTIONS for name in names]
        widgets = {
            "fecha_compromiso": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }

    sections = IMPACTO_SECTIONS

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["responsable"].queryset = User.objects.filter(
            memberships__client=self.client, memberships__is_active=True,
        ).order_by("first_name", "email")
        self.fields["responsable_categoria"].queryset = active_or_current(
            CategoriaResponsable.objects.all(), self.instance.responsable_categoria_id
        )


class PriorityOverrideForm(forms.ModelForm):
    class Meta:
        model = Impacto
        fields = ["prioridad_ajustada", "prioridad_justificacion"]
        widgets = {"prioridad_justificacion": forms.Textarea(attrs={"rows": 2})}
        labels = {"prioridad_ajustada": _("Ajustar prioridad")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["prioridad_ajustada"].choices = [
            ("", _("Sin ajuste (usar la calculada)")),
            *[(p.value, p.label) for p in rules.Priority],
        ]

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("prioridad_ajustada"):
            if not (cleaned.get("prioridad_justificacion") or "").strip():
                self.add_error("prioridad_justificacion",
                               _("Justifica el ajuste de prioridad."))
        else:
            cleaned["prioridad_justificacion"] = ""
        return cleaned


class ComentarioForm(forms.ModelForm):
    class Meta:
        model = Comentario
        fields = ["texto"]
        widgets = {"texto": forms.Textarea(attrs={"rows": 2})}
        labels = {"texto": ""}


class AdjuntoForm(BaseAdjuntoForm):
    class Meta(BaseAdjuntoForm.Meta):
        model = Adjunto


class FotoForm(forms.ModelForm):
    class Meta:
        model = Foto
        fields = ["tiempo", "nota"]


class FiltroForm(forms.Form):
    ALERTAS = [
        ("", _("Todas")),
        ("p1_sin_criterio", _("P1 sin criterio de cierre")),
        ("sin_criterio", _("Sin criterio de cierre")),
        ("extrema", _("Severidad extrema")),
        ("sugerido", _("Con grupo sugerido por revisar")),
        ("descubiertos", _("Descubiertos (activos y sin actividades)")),
        ("bloqueados", _("Bloqueados (dependen de impactos abiertos)")),
    ]

    q = forms.CharField(label=_("Buscar"), required=False)
    estado = forms.ChoiceField(label=_("Estado"), required=False,
                               choices=[("", _("Todos")), *Estado.choices])
    prioridad = forms.ChoiceField(label=_("Prioridad"), required=False,
                                  choices=[("", _("Todas")),
                                           *[(p.value, p.label) for p in rules.Priority]])
    grupo = forms.ModelChoiceField(label=_("Grupo"), required=False,
                                   queryset=GrupoImpactado.unscoped.none(),
                                   empty_label=_("Todos"))
    tiempo = forms.ModelChoiceField(label=_("Tiempo"), required=False, queryset=None,
                                    empty_label=_("Todos"))
    alerta = forms.ChoiceField(label=_("Alertas"), required=False, choices=ALERTAS)

    def __init__(self, *args, **kwargs):
        from apps.catalogs.models import SystemCatalog, SystemCatalogItem

        super().__init__(*args, **kwargs)
        self.fields["grupo"].queryset = GrupoImpactado.objects.all()
        self.fields["tiempo"].queryset = SystemCatalogItem.objects.of(SystemCatalog.TIEMPO)

    def filter(self, qs):
        from django.db.models import Q

        if not self.is_valid():
            return qs
        d = self.cleaned_data
        if d["q"]:
            qs = qs.filter(Q(titulo__icontains=d["q"]) | Q(descripcion__icontains=d["q"]))
        if d["estado"]:
            qs = qs.filter(estado=d["estado"])
        if d["prioridad"]:
            qs = qs.filter(prioridad=d["prioridad"])
        if d["grupo"]:
            qs = qs.filter(grupo=d["grupo"])
        if d["tiempo"]:
            qs = qs.filter(tiempo=d["tiempo"])
        sin_criterio = sin_criterio_q()
        match d["alerta"]:
            case "p1_sin_criterio":
                qs = qs.filter(sin_criterio, prioridad=rules.Priority.P1)
            case "sin_criterio":
                qs = qs.filter(sin_criterio)
            case "extrema":
                qs = qs.filter(severidad=rules.EXTREME_SEVERITY)
            case "sugerido":
                qs = qs.filter(grupo__isnull=True).exclude(grupo_sugerido="")
            case "bloqueados":
                qs = qs.filter(dependencias__depende_de__estado__in=OPEN_STATES).distinct()
            case "descubiertos":
                qs = qs.filter(estado__in=ACTIVE_STATES, actividades__isnull=True)
        return qs
