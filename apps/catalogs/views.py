"""Client catalog configuration, under /c/<client_slug>/configuracion/."""

from django import forms
from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.decorators.http import require_POST

from apps.core.decorators import client_admin_required
from apps.core.models import Membership

from .forms import client_catalog_form
from .models import Canal, Cargo, CategoriaResponsable, GrupoImpactado, UnidadOrganizacional

BASE_FIELDS = ["name", "description", "order"]

# URL segment -> (model, form, help shown on the list page)
CLIENT_CATALOGS = {
    "grupos": (
        GrupoImpactado,
        client_catalog_form(GrupoImpactado, ["name", "description", "personas", "order"]),
        gettext_lazy("Grupos de personas a los que afecta el cambio. Agrupan impactos, "
                     "actividades, tickets y resultados."),
    ),
    "unidades": (
        UnidadOrganizacional,
        client_catalog_form(UnidadOrganizacional, ["kind", *BASE_FIELDS]),
        gettext_lazy("Áreas, oficinas, sucursales y departamentos del cliente."),
    ),
    "cargos": (
        Cargo, client_catalog_form(Cargo, BASE_FIELDS),
        gettext_lazy("Cargos de las personas, para agrupar resultados."),
    ),
    "canales": (
        Canal, client_catalog_form(Canal, BASE_FIELDS),
        gettext_lazy("Canales y formatos de las actividades de la Ruta: intranet, reunión de "
                     "equipo, correo del gerente, taller…"),
    ),
    "categorias-responsable": (
        CategoriaResponsable, client_catalog_form(CategoriaResponsable, BASE_FIELDS),
        gettext_lazy("Por ejemplo: equipo técnico, PMO, gerencia."),
    ),
}


def _catalog(key):
    try:
        return CLIENT_CATALOGS[key]
    except KeyError:
        raise Http404 from None


@client_admin_required
def config_index(request, client_slug):
    catalogs = [
        {"key": key, "name": model._meta.verbose_name_plural, "help": help_text,
         "count": model.objects.filter(is_active=True).count()}
        for key, (model, _form, help_text) in CLIENT_CATALOGS.items()
    ]
    return render(request, "catalogs/config_index.html", {"catalogs": catalogs})


@client_admin_required
def catalog_list(request, client_slug, catalog):
    model, form_class, help_text = _catalog(catalog)
    form = form_class(request.POST or None)
    if request.method == "POST" and form.is_valid():
        item = form.save()
        messages.success(request, _("«%(name)s» agregado.") % {"name": item.name})
        return redirect("catalogs:list", client_slug=client_slug, catalog=catalog)
    return render(request, "catalogs/config_list.html", {
        "catalog": catalog,
        "name": model._meta.verbose_name_plural,
        "help": help_text,
        "items": model.objects.all(),
        "has_kind": "kind" in form_class.base_fields,
        "form": form,
    })


@client_admin_required
def catalog_edit(request, client_slug, catalog, pk):
    model, form_class, _help = _catalog(catalog)
    item = get_object_or_404(model.objects, pk=pk)
    form = form_class(request.POST or None, instance=item)
    if request.method == "POST":
        if "toggle" in request.POST:
            item.is_active = not item.is_active
            item.save(update_fields=["is_active"])
            return redirect("catalogs:list", client_slug=client_slug, catalog=catalog)
        if form.is_valid():
            form.save()
            messages.success(request, _("Cambios guardados."))
            return redirect("catalogs:list", client_slug=client_slug, catalog=catalog)
    return render(request, "catalogs/config_edit.html", {
        "catalog": catalog, "name": model._meta.verbose_name_plural,
        "item": item, "form": form,
    })


class MemberGroupsForm(forms.ModelForm):
    # Declared explicitly: a generated field would query groups before any client is active.
    grupos = forms.ModelMultipleChoiceField(
        label=gettext_lazy("Grupos"), queryset=GrupoImpactado.unscoped.none(), required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = Membership
        fields = ["grupos"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["grupos"].queryset = GrupoImpactado.objects.filter(is_active=True)


@client_admin_required
def personas(request, client_slug):
    memberships = (
        Membership.objects.filter(client=request.client, is_active=True)
        .select_related("user").prefetch_related("grupos").order_by("role", "user__email")
    )
    return render(request, "catalogs/personas.html", {
        "rows": [(m, MemberGroupsForm(instance=m, prefix=f"m{m.pk}")) for m in memberships],
    })


@client_admin_required
@require_POST
def persona_grupos(request, client_slug, pk):
    membership = get_object_or_404(Membership, client=request.client, pk=pk)
    form = MemberGroupsForm(request.POST, instance=membership, prefix=f"m{pk}")
    if form.is_valid():
        form.save()
        messages.success(request, _("Grupos de %(user)s actualizados.")
                         % {"user": membership.user.display_name})
    return redirect("catalogs:personas", client_slug=client_slug)
