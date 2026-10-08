from django import forms
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.catalogs.models import GrupoImpactado, SystemCatalog, SystemCatalogItem
from apps.matriz.forms import active_or_current
from apps.matriz.models import Estado, Impacto

from .models import EstadoTicket, Ticket, Urgencia

DATE = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")


class TicketChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f"{obj.codigo} · {obj.titulo}"


class TicketForm(forms.ModelForm):
    # Tenant-scoped choices are filled in __init__ (see BaseImpactoForm).
    grupo = forms.ModelChoiceField(
        label=_("Grupo impactado"), queryset=GrupoImpactado.unscoped.none(), required=False
    )
    impacto = TicketChoiceField(
        label=_("Impacto vinculado"),
        queryset=Impacto.unscoped.none(),
        required=False,
        help_text=_("Opcional."),
    )
    recurrente_de = TicketChoiceField(
        label=_("Repite el caso"),
        queryset=Ticket.unscoped.none(),
        required=False,
        help_text=Ticket._meta.get_field("recurrente_de").help_text,
    )

    class Meta:
        model = Ticket
        fields = [
            "titulo",
            "descripcion",
            "categoria",
            "urgencia",
            "grupo",
            "impacto",
            "caso_cliente",
            "recurrente_de",
        ]
        widgets = {"descripcion": forms.Textarea(attrs={"rows": 4}), "urgencia": forms.RadioSelect}

    def __init__(self, *args, classify=False, see_matrix=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["grupo"].queryset = active_or_current(
            GrupoImpactado.objects.all(), self.instance.grupo_id
        )
        if see_matrix:
            self.fields["impacto"].queryset = Impacto.objects.exclude(
                Q(estado=Estado.DESCARTADO) & ~Q(pk=self.instance.impacto_id)
            ).order_by("numero")
        else:
            del self.fields["impacto"]
        if classify:
            self.fields["recurrente_de"].queryset = Ticket.objects.exclude(
                pk=self.instance.pk
            ).order_by("-numero")
        else:
            del self.fields["recurrente_de"]


class CasoClienteForm(forms.ModelForm):
    class Meta:
        model = Ticket
        fields = ["caso_cliente"]


class ComentarioForm(forms.Form):
    texto = forms.CharField(label="", widget=forms.Textarea(attrs={"rows": 2}))


class FiltroForm(forms.Form):
    q = forms.CharField(label=_("Buscar"), required=False)
    estado = forms.ChoiceField(
        label=_("Estado"),
        required=False,
        choices=[("", _("Todos")), ("abiertos", _("Abiertos")), *EstadoTicket.choices],
    )
    categoria = forms.ModelChoiceField(
        label=_("Categoría"), queryset=None, required=False, empty_label=_("Todas")
    )
    urgencia = forms.ChoiceField(
        label=_("Urgencia"), required=False, choices=[("", _("Todas")), *Urgencia.choices]
    )
    grupo = forms.ModelChoiceField(
        label=_("Grupo"),
        queryset=GrupoImpactado.unscoped.none(),
        required=False,
        empty_label=_("Todos"),
    )
    sin_validar = forms.BooleanField(label=_("Sin validar"), required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["categoria"].queryset = SystemCatalogItem.objects.of(
            SystemCatalog.CATEGORIA_TICKET
        )
        self.fields["grupo"].queryset = GrupoImpactado.objects.all()

    def filter(self, qs):
        from .models import OPEN_TICKET_STATES

        if not self.is_valid():
            return qs
        d = self.cleaned_data
        if d["q"]:
            qs = qs.filter(
                Q(titulo__icontains=d["q"])
                | Q(descripcion__icontains=d["q"])
                | Q(caso_cliente__icontains=d["q"])
            )
        if d["estado"] == "abiertos":
            qs = qs.filter(estado__in=OPEN_TICKET_STATES)
        elif d["estado"]:
            qs = qs.filter(estado=d["estado"])
        for name in ("categoria", "urgencia", "grupo"):
            if d[name]:
                qs = qs.filter(**{name: d[name]})
        if d["sin_validar"]:
            qs = qs.filter(validado=False).exclude(estado=EstadoTicket.CERRADO)
        return qs


class MetricasForm(forms.Form):
    desde = forms.DateField(label=_("Desde"), required=False, widget=DATE)
    hasta = forms.DateField(label=_("Hasta"), required=False, widget=DATE)
