import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.core.models import Module, Role
from apps.core.tenancy import tenant_context
from apps.guia.models import Documento, Plantilla, Tema

pytestmark = pytest.mark.django_db


@pytest.fixture
def login_as(client, member, acme):
    def login(role, email=None):
        user, _ = member(role, client=acme, email=email or f"{role}@example.com")
        client.force_login(user)
        return user

    return login


def guia_url(slug="acme"):
    return reverse("guia:index", args=[slug])


def make_documento(client_obj, user, **kwargs):
    data = {"nombre": "Organigrama", "url": "https://example.com/org", "subido_por": user}
    data.update(kwargs)
    with tenant_context(client_obj):
        return Documento.objects.create(**data)


class TestAccess:
    @pytest.mark.parametrize("role", list(Role))
    def test_every_role_sees_the_guide(self, client, login_as, role):
        login_as(role)
        assert client.get(guia_url()).status_code == 200

    def test_module_disabled(self, client, login_as, acme):
        acme.enabled_modules = [m for m in Module.values if m != Module.GUIA]
        acme.save()
        login_as(Role.ADMINISTRACION)
        assert client.get(guia_url()).status_code == 403

    def test_anonymous_goes_to_login(self, client, acme):
        response = client.get(guia_url())
        assert response.status_code == 302
        assert reverse("login") in response["Location"]

    def test_home_card_links_to_the_guide(self, client, login_as):
        login_as(Role.CAPITAN)
        response = client.get(reverse("client_home", args=["acme"]))
        assert guia_url() in response.content.decode()


class TestContent:
    def test_shows_catalogs_scales_and_rules(self, client, login_as):
        login_as(Role.CAPITAN)
        html = client.get(guia_url()).content.decode()
        assert 'id="catalogo-tiempo"' in html
        assert "Travesía" in html
        assert 'id="escala-magnitud"' in html
        assert 'id="calculos"' in html

    def test_priority_matrix_matches_parte_b(self, client, login_as):
        """§3.4: rows from Crítico down to Bajo, columns Leve to Profundo."""
        login_as(Role.CAPITAN)
        matrix = client.get(guia_url()).context["calculos"]["matrix"]
        assert [(r["band"], r["cells"]) for r in matrix] == [
            ("Crítico", ["P2", "P2", "P1", "P1"]),
            ("Alto", ["P3", "P2", "P2", "P1"]),
            ("Medio", ["P4", "P3", "P2", "P2"]),
            ("Bajo", ["P4", "P4", "P3", "P2"]),
        ]

    def test_only_active_topics_and_templates(self, client, login_as):
        Tema.objects.create(slug="regla", titulo="Regla de decisión", contenido="Texto")
        Tema.objects.create(slug="vieja", titulo="Tema retirado", contenido="x", is_active=False)
        Plantilla.objects.create(nombre="Plan de comunicación", url="https://example.com/p")
        login_as(Role.LIDER_AREA)
        html = client.get(guia_url()).content.decode()
        assert 'id="tema-regla"' in html
        assert "Tema retirado" not in html
        assert "Plan de comunicación" in html

    def test_topic_content_is_escaped(self, client, login_as):
        Tema.objects.create(slug="x", titulo="X", contenido="<script>alert(1)</script>")
        login_as(Role.CAPITAN)
        assert "<script>alert(1)" not in client.get(guia_url()).content.decode()


class TestPlantillas:
    def test_download_file(self, client, login_as):
        plantilla = Plantilla.objects.create(
            nombre="Matriz vacía", archivo=SimpleUploadedFile("matriz.csv", b"a,b")
        )
        login_as(Role.CAPITAN)
        response = client.get(reverse("guia:descargar_plantilla", args=["acme", plantilla.pk]))
        assert response.status_code == 200
        assert b"".join(response.streaming_content) == b"a,b"

    def test_inactive_is_not_served(self, client, login_as):
        plantilla = Plantilla.objects.create(
            nombre="Vieja", archivo=SimpleUploadedFile("v.csv", b"x"), is_active=False
        )
        login_as(Role.CAPITAN)
        url = reverse("guia:descargar_plantilla", args=["acme", plantilla.pk])
        assert client.get(url).status_code == 404


class TestDocumentos:
    def test_admin_adds_a_link(self, client, login_as, acme):
        login_as(Role.ADMINISTRACION)
        response = client.post(
            reverse("guia:agregar_documento", args=["acme"]),
            {"url": "https://example.com/org", "nombre": "Organigrama"},
        )
        assert response.status_code == 302
        with tenant_context(acme):
            assert Documento.objects.get().nombre == "Organigrama"

    def test_admin_uploads_and_deletes_a_file(self, client, login_as, acme):
        login_as(Role.ADMINISTRACION)
        client.post(
            reverse("guia:agregar_documento", args=["acme"]),
            {"archivo": SimpleUploadedFile("politica.pdf", b"%PDF")},
        )
        with tenant_context(acme):
            documento = Documento.objects.get()
        storage, name = documento.archivo.storage, documento.archivo.name
        download = client.get(reverse("guia:descargar_documento", args=["acme", documento.pk]))
        assert b"".join(download.streaming_content) == b"%PDF"

        client.post(reverse("guia:eliminar_documento", args=["acme", documento.pk]))
        with tenant_context(acme):
            assert not Documento.objects.exists()
        assert not storage.exists(name)

    @pytest.mark.parametrize("role", [Role.EQUIPO_CAMBIO, Role.CAPITAN, Role.PATROCINADOR])
    def test_viewers_cannot_manage(self, client, login_as, acme, equipo, role):
        documento = make_documento(acme, equipo)
        login_as(role)
        add = client.post(
            reverse("guia:agregar_documento", args=["acme"]), {"url": "https://example.com"}
        )
        delete = client.post(reverse("guia:eliminar_documento", args=["acme", documento.pk]))
        assert (add.status_code, delete.status_code) == (403, 403)
        assert "Agregar documento" not in client.get(guia_url()).content.decode()

    def test_other_clients_documents_are_isolated(self, client, login_as, make_client, equipo):
        otro = make_client("otro")
        documento = make_documento(otro, equipo, nombre="Secreto de otro")
        login_as(Role.ADMINISTRACION)
        assert "Secreto de otro" not in client.get(guia_url()).content.decode()
        url = reverse("guia:descargar_documento", args=["acme", documento.pk])
        assert client.get(url).status_code == 404
        delete = client.post(reverse("guia:eliminar_documento", args=["acme", documento.pk]))
        assert delete.status_code == 404


class TestContextualHelp:
    def form_html(self, client):
        return client.get(reverse("matriz:crear", args=["acme"])).content.decode()

    def test_catalog_and_scale_fields_link_to_the_guide(self, client, login_as):
        login_as(Role.EQUIPO_CAMBIO)
        html = self.form_html(client)
        assert f'href="{guia_url()}#catalogo-tiempo"' in html
        assert f'href="{guia_url()}#escala-magnitud"' in html

    def test_no_links_when_the_guide_is_disabled(self, client, login_as, acme):
        acme.enabled_modules = [m for m in Module.values if m != Module.GUIA]
        acme.save()
        login_as(Role.EQUIPO_CAMBIO)
        assert "guia-link" not in self.form_html(client)


class TestPlataforma:
    def test_only_platform_admins(self, client, login_as):
        login_as(Role.ADMINISTRACION)
        assert client.get(reverse("plataforma:guia_index")).status_code == 403

    def test_create_topic_shows_on_client_guide(self, client, platform_admin, login_as):
        client.force_login(platform_admin)
        response = client.post(
            reverse("plataforma:tema_create"),
            {
                "titulo": "Frentes",
                "slug": "frentes",
                "contenido": "Cuatro frentes.",
                "orden": 1,
                "is_active": "on",
            },
        )
        assert response.status_code == 302
        login_as(Role.CAPITAN)
        assert 'id="tema-frentes"' in client.get(guia_url()).content.decode()

    def test_template_needs_file_or_link(self, client, platform_admin):
        client.force_login(platform_admin)
        response = client.post(
            reverse("plataforma:plantilla_create"), {"nombre": "Vacía", "orden": 0}
        )
        assert response.status_code == 200
        assert not Plantilla.objects.exists()
