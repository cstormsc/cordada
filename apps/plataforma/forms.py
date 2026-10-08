from django import forms
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from apps.core.models import Client, Membership, Module, Role

RESERVED_SLUGS = {"admin", "plataforma", "static", "media", "api", "nuevo"}


class ClientForm(forms.ModelForm):
    enabled_modules = forms.MultipleChoiceField(
        label=_("Módulos activos"),
        choices=Module.choices,
        widget=forms.CheckboxSelectMultiple,
        required=False,
    )

    class Meta:
        model = Client
        fields = ["name", "slug", "is_active", "enabled_modules"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["slug"].required = False
        self.fields["slug"].help_text = _(
            "Se usa en la dirección web: /c/<identificador>/. Si lo dejas vacío, "
            "se genera a partir del nombre."
        )
        if self.instance.pk:
            # Changing it breaks links people already have.
            self.fields["slug"].disabled = True
        else:
            del self.fields["is_active"]  # new clients start active
            self.initial.setdefault("enabled_modules", list(Module.values))

    def clean_slug(self):
        if self.instance.pk:
            return self.instance.slug
        slug = self.cleaned_data.get("slug") or slugify(self.cleaned_data.get("name", ""))
        slug = slugify(slug)
        if not slug:
            raise forms.ValidationError(_("Indica un identificador."))
        if slug in RESERVED_SLUGS:
            raise forms.ValidationError(_("Ese identificador está reservado."))
        if Client.objects.filter(slug=slug).exists():
            raise forms.ValidationError(_("Ya existe un cliente con ese identificador."))
        return slug


class InviteForm(forms.Form):
    email = forms.EmailField(label=_("Correo"))
    role = forms.ChoiceField(label=_("Rol"), choices=Role.choices)

    def __init__(self, *args, client, **kwargs):
        self.client = client
        super().__init__(*args, **kwargs)

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if Membership.objects.filter(
            client=self.client, user__email__iexact=email, is_active=True
        ).exists():
            raise forms.ValidationError(_("Esa persona ya es miembro de este cliente."))
        return email


class MembershipRoleForm(forms.ModelForm):
    class Meta:
        model = Membership
        fields = ["role"]
