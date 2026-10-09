from django import forms
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.catalogs.models import Canal, GrupoImpactado, SystemCatalog, SystemCatalogItem
from apps.core.attachments import AdjuntoForm
from apps.core.models import User
from apps.matriz.forms import MemberChoiceField, active_or_current
from apps.matriz.models import Estado, Impacto

from .models import DONE, Actividad, Cumplimiento, EstadoActividad, Evidencia

DATE = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")


class ImpactoChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj):
        return f"{obj.codigo} · {obj.titulo}"


class ActividadForm(forms.ModelForm):
    # Tenant-scoped choices are filled in __init__ (see BaseImpactoForm).
    grupos = forms.ModelMultipleChoiceField(
        label=_("Grupos impactados"),
        queryset=GrupoImpactado.unscoped.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    impactos = ImpactoChoiceField(
        label=_("Impactos"),
        queryset=Impacto.unscoped.none(),
        required=False,
        help_text=Actividad._meta.get_field("impactos").help_text,
        widget=forms.SelectMultiple(attrs={"size": 6}),
    )
    canal = forms.ModelChoiceField(
        label=_("Canal o formato"), queryset=Canal.unscoped.none(), required=False
    )
    responsable = MemberChoiceField(
        label=_("Responsable"), queryset=User.objects.none(), required=False
    )

    class Meta:
        model = Actividad
        fields = [
            "titulo",
            "descripcion",
            "frente",
            "tiempo",
            "impactos",
            "grupos",
            "responsable",
            "no_planificada",
            "fecha_planificada",
            "fecha_real",
            "estado",
            "canal",
            "vocero",
            "evidencia",
            "indicador",
        ]
        widgets = {
            "fecha_planificada": DATE,
            "fecha_real": DATE,
            "descripcion": forms.Textarea(attrs={"rows": 3}),
            "evidencia": forms.Textarea(attrs={"rows": 3}),
        }

    sections = [
        (_("Actividad"), ["titulo", "descripcion", "frente", "tiempo", "canal", "vocero"]),
        (_("A qué responde"), ["impactos", "grupos", "indicador"]),
        (
            _("Plan y ejecución"),
            [
                "responsable",
                "no_planificada",
                "fecha_planificada",
                "fecha_real",
                "estado",
                "evidencia",
            ],
        ),
    ]

    def __init__(self, *args, client, **kwargs):
        super().__init__(*args, **kwargs)
        pk = self.instance.pk
        self.fields["grupos"].queryset = GrupoImpactado.objects.filter(
            Q(is_active=True) | Q(actividades=pk) if pk else Q(is_active=True)
        ).distinct()
        self.fields["impactos"].queryset = (
            Impacto.objects.filter(
                ~Q(estado=Estado.DESCARTADO) | Q(actividades=pk)
                if pk
                else ~Q(estado=Estado.DESCARTADO)
            )
            .distinct()
            .order_by("numero")
        )
        self.fields["canal"].queryset = active_or_current(
            Canal.objects.all(), self.instance.canal_id
        )
        self.fields["responsable"].queryset = User.objects.members_of(client)

    def get_sections(self):
        return [(t, [self[n] for n in names if n in self.fields]) for t, names in self.sections]

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("no_planificada") and not cleaned.get("fecha_planificada"):
            self.add_error(
                "fecha_planificada",
                _("Indica la fecha planificada, o marca la actividad como no planificada."),
            )
        if cleaned.get("estado") in DONE and not cleaned.get("fecha_real"):
            self.add_error("fecha_real", _("Indica cuándo se hizo."))
        fecha_real = cleaned.get("fecha_real")
        if fecha_real and fecha_real > timezone.localdate():
            self.add_error("fecha_real", _("La fecha real no puede ser futura."))
        frente = cleaned.get("frente")
        if frente and frente.code != "comunicacion":
            cleaned["vocero"] = ""
        return cleaned


class EvidenciaForm(AdjuntoForm):
    class Meta(AdjuntoForm.Meta):
        model = Evidencia


def _tiempo_qs():
    return SystemCatalogItem.objects.of(SystemCatalog.TIEMPO)


def _frente_qs():
    return SystemCatalogItem.objects.of(SystemCatalog.FRENTE)


class FiltroForm(forms.Form):
    q = forms.CharField(label=_("Buscar"), required=False)
    frente = forms.ModelChoiceField(
        label=_("Frente"), queryset=None, required=False, empty_label=_("Todos")
    )
    tiempo = forms.ModelChoiceField(
        label=_("Tiempo"), queryset=None, required=False, empty_label=_("Todos")
    )
    estado = forms.ChoiceField(
        label=_("Estado"), required=False, choices=[("", _("Todos")), *EstadoActividad.choices]
    )
    cumplimiento = forms.ChoiceField(
        label=_("Cumplimiento"), required=False, choices=[("", _("Todos")), *Cumplimiento.choices]
    )
    grupo = forms.ModelChoiceField(
        label=_("Grupo"),
        queryset=GrupoImpactado.unscoped.none(),
        required=False,
        empty_label=_("Todos"),
    )
    huerfanas = forms.BooleanField(label=_("Solo huérfanas"), required=False)

    def __init__(self, *args, grupos=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["frente"].queryset = _frente_qs()
        self.fields["tiempo"].queryset = _tiempo_qs()
        self.fields["grupo"].queryset = (
            grupos if grupos is not None else GrupoImpactado.objects.all()
        )

    def filter(self, qs):
        if not self.is_valid():
            return qs
        d = self.cleaned_data
        if d["q"]:
            qs = qs.filter(Q(titulo__icontains=d["q"]) | Q(descripcion__icontains=d["q"]))
        for name in ("frente", "tiempo", "estado", "cumplimiento"):
            if d[name]:
                qs = qs.filter(**{name: d[name]})
        if d["grupo"]:
            qs = qs.filter(grupos=d["grupo"])
        if d["huerfanas"]:
            qs = qs.huerfanas()
        return qs


class InformeForm(forms.Form):
    """Compliance report: by stage (stage sessions) or by month (sponsor summary)."""

    tiempo = forms.ModelChoiceField(
        label=_("Etapa"), queryset=None, required=False, empty_label=_("Todas")
    )
    mes = forms.CharField(
        label=_("Mes"),
        required=False,
        widget=forms.DateInput(attrs={"type": "month"}),
        help_text=_("Para el resumen mensual."),
    )
    frente = forms.ModelChoiceField(
        label=_("Frente"), queryset=None, required=False, empty_label=_("Todos")
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tiempo"].queryset = _tiempo_qs()
        self.fields["frente"].queryset = _frente_qs()

    def clean_mes(self):
        mes = self.cleaned_data.get("mes")
        if not mes:
            return None
        try:
            year, month = (int(p) for p in mes.split("-"))
            return timezone.datetime(year, month, 1).date()
        except (ValueError, TypeError):
            raise forms.ValidationError(_("Mes no válido (AAAA-MM).")) from None
