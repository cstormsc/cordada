from django import forms
from django.utils.translation import gettext_lazy as _

from apps.catalogs.models import GrupoImpactado, SystemCatalog, SystemCatalogItem

from .indicators import INDICATORS
from .models import IndicadorConfig, ValorManual


class FiltroForm(forms.Form):
    tiempo = forms.ModelChoiceField(label=_("Tiempo del marco"), queryset=None, required=False,
                                    empty_label=_("Todos"))
    grupo = forms.ModelChoiceField(label=_("Grupo"), queryset=GrupoImpactado.unscoped.none(),
                                   required=False, empty_label=_("Todos"))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tiempo"].queryset = SystemCatalogItem.objects.of(SystemCatalog.TIEMPO)
        self.fields["grupo"].queryset = GrupoImpactado.objects.filter(is_active=True)


class ValorManualForm(forms.ModelForm):
    key = forms.ChoiceField(label=_("Indicador"),
                            choices=[(i.key, i.nombre) for i in INDICATORS if i.manual])
    grupo = forms.ModelChoiceField(label=_("Grupo"), queryset=GrupoImpactado.unscoped.none(),
                                   required=False, empty_label=_("Toda la organización"))

    class Meta:
        model = ValorManual
        fields = ["key", "fecha", "valor", "grupo", "nota"]
        widgets = {"fecha": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")}
        help_texts = {"valor": _("Porcentajes de 0 a 100; el diagnóstico, en puntos.")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["grupo"].queryset = GrupoImpactado.objects.filter(is_active=True)


class IndicadorConfigForm(forms.ModelForm):
    class Meta:
        model = IndicadorConfig
        fields = ["verde", "amarillo", "responsable", "frecuencia", "activo"]

    def __init__(self, *args, indicator, **kwargs):
        super().__init__(*args, **kwargs)
        self.indicator = indicator
        if indicator.higher_is_better is None:
            del self.fields["verde"], self.fields["amarillo"]
        elif indicator.higher_is_better is False:
            self.fields["verde"].label = _("en meta hasta")
            self.fields["amarillo"].label = _("atención hasta")

    def clean(self):
        cleaned = super().clean()
        v, a = cleaned.get("verde"), cleaned.get("amarillo")
        if v is not None and a is not None:
            wrong = a > v if self.indicator.higher_is_better else a < v
            if wrong:
                self.add_error("amarillo", _("Debe estar entre el umbral rojo y el verde."))
        return cleaned
