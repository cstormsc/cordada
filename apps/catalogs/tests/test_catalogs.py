import pytest
from django import forms
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from apps.catalogs.models import (
    GrupoImpactado,
    Scale,
    SystemCatalog,
    SystemCatalogItem,
    UnidadOrganizacional,
)
from apps.core.models import Role
from apps.core.tenancy import tenant_context
from apps.core.tests.tenantapp.models import Note

pytestmark = pytest.mark.django_db


class TestSeededSystemCatalogs:
    def codes(self, catalog):
        return list(SystemCatalogItem.objects.of(catalog).values_list("code", flat=True))

    def test_tiempos_in_order(self):
        assert self.codes(SystemCatalog.TIEMPO) == ["horizonte", "travesia", "cumbre", "legado"]

    def test_fixed_lists_from_the_document(self):
        assert len(self.codes(SystemCatalog.TIPO_IMPACTO)) == 6
        assert len(self.codes(SystemCatalog.CATEGORIA_TICKET)) == 7
        assert len(self.codes(SystemCatalog.TIPO_CAMBIO_CONOCIMIENTO)) == 4
        assert len(self.codes(SystemCatalog.EVIDENCIA_CIERRE)) == 5

    def test_origin_is_still_to_be_defined(self):
        assert self.codes(SystemCatalog.ORIGEN) == []

    @pytest.mark.parametrize(("code", "labels"), [
        ("magnitud", ["Leve", "Moderado", "Alto", "Profundo"]),
        ("probabilidad", ["Improbable", "Posible", "Probable", "Casi segura"]),
        ("severidad", ["Menor", "Notable", "Mayor", "Extrema"]),
    ])
    def test_defined_scales(self, code, labels):
        scale = Scale.objects.get(code=code)
        assert [lvl.label for lvl in scale.levels.all()] == labels
        assert [v for v, _ in scale.choices()] == [1, 2, 3, 4]
        assert scale.is_defined

    @pytest.mark.parametrize("code", ["resistencia", "preparacion"])
    def test_pending_scales_exist_without_levels(self, code):
        assert not Scale.objects.get(code=code).is_defined


class TestSystemCatalogField:
    def test_rejects_items_from_another_catalog(self, make_client):
        with tenant_context(make_client()):
            note = Note(text="x", tipo=SystemCatalogItem.objects.get(
                catalog=SystemCatalog.TIEMPO, code="cumbre"))
            with pytest.raises(ValidationError):
                note.full_clean(exclude=["client"])

    def test_form_only_offers_active_items_of_its_catalog(self):
        SystemCatalogItem.objects.filter(code="cultura").update(is_active=False)
        form = forms.modelform_factory(Note, fields=["tipo"])()
        codes = set(form.fields["tipo"].queryset.values_list("code", flat=True))
        assert codes == {"proceso", "tecnologia", "rol_funcion", "estructura", "conocimiento"}


class TestClientCatalogModels:
    def test_isolated_per_client(self, make_client):
        acme, globex = make_client("acme"), make_client("globex")
        with tenant_context(acme):
            GrupoImpactado.objects.create(name="Cobranzas")
        with tenant_context(globex):
            assert not GrupoImpactado.objects.exists()
            GrupoImpactado.objects.create(name="Cobranzas")  # same name, other client

    def test_names_unique_per_client_ignoring_case(self, make_client):
        with tenant_context(make_client()):
            GrupoImpactado.objects.create(name="Cobranzas")
            with pytest.raises(IntegrityError):
                GrupoImpactado.objects.create(name="cobranzas")

    def test_same_unit_name_allowed_for_different_kinds(self, make_client):
        with tenant_context(make_client()):
            K = UnidadOrganizacional.Kind
            UnidadOrganizacional.objects.create(name="Norte", kind=K.SUCURSAL)
            UnidadOrganizacional.objects.create(name="Norte", kind=K.AREA)

    def test_changes_are_recorded(self, make_client):
        with tenant_context(make_client()):
            grupo = GrupoImpactado.objects.create(name="Cobranzas")
            grupo.name = "Cobranza y recaudación"
            grupo.save()
            assert grupo.history.count() == 2


class TestClientConfigViews:
    url = "/c/acme/configuracion/grupos/"

    @pytest.fixture
    def admin(self, client, member):
        user, acme = member(Role.ADMINISTRACION)
        client.force_login(user)
        return acme

    @pytest.mark.parametrize("role", [r for r in Role if r != Role.ADMINISTRACION])
    def test_only_administracion_configures(self, client, member, role):
        user, _ = member(role)
        client.force_login(user)
        assert client.get("/c/acme/configuracion/").status_code == 403

    def test_add_edit_and_deactivate(self, client, admin):
        assert client.post(self.url, {"name": "Cobranzas", "order": 0}).status_code == 302
        with tenant_context(admin):
            grupo = GrupoImpactado.objects.get()
        edit = f"{self.url}{grupo.pk}/"
        client.post(edit, {"name": "Cobranza", "description": "Equipo de cobranza", "order": 1})
        client.post(edit, {"toggle": "1"})
        grupo.refresh_from_db()
        assert (grupo.name, grupo.description, grupo.is_active) == (
            "Cobranza", "Equipo de cobranza", False)
        assert grupo.client == admin

    def test_duplicate_name_is_a_form_error(self, client, admin):
        client.post(self.url, {"name": "Cobranzas", "order": 0})
        response = client.post(self.url, {"name": "COBRANZAS", "order": 0})
        assert response.status_code == 200
        assert "Ya existe uno con ese nombre" in response.content.decode()

    def test_units_need_a_kind_and_allow_same_name_per_kind(self, client, admin):
        url = "/c/acme/configuracion/unidades/"
        client.post(url, {"kind": "area", "name": "Norte", "order": 0})
        client.post(url, {"kind": "sucursal", "name": "Norte", "order": 0})
        response = client.post(url, {"kind": "area", "name": "norte", "order": 0})
        assert "Ya existe uno con ese nombre" in response.content.decode()
        with tenant_context(admin):
            assert UnidadOrganizacional.objects.count() == 2

    def test_cannot_edit_another_clients_item(self, client, admin, make_client):
        with tenant_context(make_client("globex")):
            other = GrupoImpactado.objects.create(name="Ajeno")
        assert client.get(f"{self.url}{other.pk}/").status_code == 404

    def test_unknown_catalog_is_404(self, client, admin):
        assert client.get("/c/acme/configuracion/nada/").status_code == 404
