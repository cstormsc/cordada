from django import forms
from django.contrib.auth.password_validation import validate_password
from django.utils.translation import gettext_lazy as _

from apps.catalogs.models import Cargo, UnidadOrganizacional


def puesto_querysets(client):
    """Job titles and departments a member of this client can have (its own catalogs)."""
    return (
        Cargo.unscoped.filter(client=client, is_active=True),
        UnidadOrganizacional.unscoped.filter(
            client=client, kind=UnidadOrganizacional.Kind.DEPARTAMENTO, is_active=True
        ),
    )


class PuestoFieldsMixin:
    """Adds cargo and departamento, chosen from the client's catalogs. Both are optional:
    a new client may not have filled its catalogs yet."""

    def add_puesto_fields(self, client):
        cargos, departamentos = puesto_querysets(client)
        self.fields["cargo"] = forms.ModelChoiceField(
            label=_("Cargo"), queryset=cargos, required=False
        )
        self.fields["departamento"] = forms.ModelChoiceField(
            label=_("Departamento"), queryset=departamentos, required=False
        )


class ConfirmPuestoForm(PuestoFieldsMixin, forms.Form):
    """For invitees who already have an account: they only confirm their position."""

    def __init__(self, *args, client, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_puesto_fields(client)


class AcceptInvitationForm(PuestoFieldsMixin, forms.Form):
    """For invitees without an account yet."""

    first_name = forms.CharField(label=_("Nombre"), max_length=150)
    last_name = forms.CharField(label=_("Apellido"), max_length=150)
    password1 = forms.CharField(label=_("Contraseña"), widget=forms.PasswordInput)
    password2 = forms.CharField(label=_("Repite la contraseña"), widget=forms.PasswordInput)

    def __init__(self, *args, client, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_puesto_fields(client)
        # Name first, then position, then password.
        self.order_fields(["first_name", "last_name", "cargo", "departamento"])

    def clean(self):
        cleaned = super().clean()
        p1, p2 = cleaned.get("password1"), cleaned.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", _("Las contraseñas no coinciden."))
        if p1:
            try:
                validate_password(p1)
            except forms.ValidationError as e:
                self.add_error("password1", e)
        return cleaned
