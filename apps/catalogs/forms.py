from django import forms
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from .models import Scale, ScaleLevel, SystemCatalogItem


class ClientCatalogForm(forms.ModelForm):
    """Base for client catalog forms; names are unique per client (and kind)."""

    unique_together_fields = ("name",)

    def clean(self):
        cleaned = super().clean()
        name = cleaned.get("name")
        if name:
            lookup = {"name__iexact": name.strip()}
            for field in self.unique_together_fields[1:]:
                lookup[field] = cleaned.get(field)
            dupes = self._meta.model.objects.filter(**lookup).exclude(pk=self.instance.pk)
            if dupes.exists():
                self.add_error("name", _("Ya existe uno con ese nombre."))
        return cleaned


def client_catalog_form(model, fields):
    form = forms.modelform_factory(
        model,
        form=ClientCatalogForm,
        fields=fields,
        widgets={"description": forms.Textarea(attrs={"rows": 2})},
    )
    form.unique_together_fields = ("name", "kind") if "kind" in fields else ("name",)
    return form


class SystemCatalogItemForm(forms.ModelForm):
    class Meta:
        model = SystemCatalogItem
        fields = ["label", "help_text", "order", "is_active"]
        widgets = {"help_text": forms.Textarea(attrs={"rows": 3})}

    def clean_label(self):
        label = " ".join(self.cleaned_data["label"].split())
        if self.instance.pk and label.lower() == self.instance.label.lower():
            return label  # unchanged: don't block items duplicated before this check
        taken = SystemCatalogItem.objects.filter(
            catalog=self.instance.catalog, label__iexact=label
        ).exclude(pk=self.instance.pk)
        if taken.exists():
            raise forms.ValidationError(_("Ya existe un ítem con ese nombre en este catálogo."))
        return label

    def save(self, commit=True):
        item = super().save(commit=False)
        if not item.pk:
            base = slugify(item.label).replace("-", "_") or "item"
            code, n = base, 2
            while SystemCatalogItem.objects.filter(catalog=item.catalog, code=code).exists():
                code, n = f"{base}_{n}", n + 1
            item.code = code
        if commit:
            item.save()
        return item


class ScaleForm(forms.ModelForm):
    class Meta:
        model = Scale
        fields = ["name", "help_text"]
        widgets = {"help_text": forms.Textarea(attrs={"rows": 2})}


class ScaleLevelForm(forms.ModelForm):
    class Meta:
        model = ScaleLevel
        fields = ["label", "definition"]
        widgets = {"definition": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["label"].required = False


def scale_level_forms(scale, data=None):
    """Always four forms, one per value; unsaved levels are created on save."""
    existing = {lvl.value: lvl for lvl in scale.levels.all()}
    return [
        ScaleLevelForm(
            data, prefix=f"nivel{v}", instance=existing.get(v) or ScaleLevel(scale=scale, value=v)
        )
        for v in range(1, 5)
    ]


def save_scale_levels(level_forms):
    """Returns an error message, or None after saving. All four levels need a name."""
    if not all(f.is_valid() for f in level_forms):
        return _("Revisa los niveles.")
    labels = [f.cleaned_data["label"].strip() for f in level_forms]
    if not any(labels) and not any(f.instance.pk for f in level_forms):
        return None  # scale still undefined; nothing to save
    if not all(labels):
        return _("Los cuatro niveles necesitan nombre.")
    for f in level_forms:
        f.save()
    return None
