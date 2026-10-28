from django import forms
from django.utils.translation import gettext_lazy as _

from apps.core.attachments import MAX_UPLOAD_MB
from apps.formularios.models import Cuestionario, EstadoCuestionario
from apps.matriz.models import Estado, Impacto

from . import cursos
from .models import Curso, Leccion, TipoLeccion


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
        fields = ["titulo", "descripcion", "impactos", "evaluacion", "fecha_limite"]
        widgets = {
            "descripcion": forms.Textarea(attrs={"rows": 3}),
            "fecha_limite": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
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


class LeccionForm(forms.ModelForm):
    url = forms.URLField(
        label=_("Enlace"),
        required=False,
        assume_scheme="https",
        help_text=Leccion._meta.get_field("url").help_text,
    )
    depende_de = forms.ModelMultipleChoiceField(
        label=_("Depende de"),
        queryset=Leccion.unscoped.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text=Leccion._meta.get_field("depende_de").help_text,
    )

    class Meta:
        model = Leccion
        fields = [
            "titulo",
            "tipo",
            "contenido",
            "url",
            "archivo",
            "minutos",
            "obligatoria",
            "depende_de",
        ]
        widgets = {
            "contenido": forms.Textarea(attrs={"rows": 10}),
        }
        help_texts = {
            "archivo": _("PDF, Office, imagen, CSV o texto. Máximo %(mb)s MB.")
            % {"mb": MAX_UPLOAD_MB},
        }

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
            for name in ("tipo", "obligatoria", "depende_de"):
                if name in self.fields:
                    self.fields[name].disabled = True

    def clean_archivo(self):
        archivo = self.cleaned_data.get("archivo")
        if archivo and archivo.size > MAX_UPLOAD_MB * 1024 * 1024:
            raise forms.ValidationError(_("El archivo supera %(mb)s MB.") % {"mb": MAX_UPLOAD_MB})
        return archivo

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

    def clean(self):
        cleaned = super().clean()
        tipo = cleaned.get("tipo")
        probe = Leccion(
            tipo=tipo,
            contenido=cleaned.get("contenido") or "",
            url=cleaned.get("url") or "",
            archivo=cleaned.get("archivo") or self.instance.archivo,
        )
        for e in cursos.lesson_errors(probe):
            field = {TipoLeccion.TEXTO: "contenido", TipoLeccion.VIDEO: "url"}.get(tipo, "archivo")
            self.add_error(field, e.capitalize() + ".")
        return cleaned
