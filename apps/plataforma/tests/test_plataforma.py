import re

import pytest
from django.core import mail
from django.core.management import call_command

from apps.core.models import Client, Invitation, Membership, Module, Role, User

pytestmark = pytest.mark.django_db


def invite_link():
    return re.search(r"http://testserver(/invitacion/\S+/)", mail.outbox[-1].body).group(1)


@pytest.fixture
def admin_client(client, platform_admin):
    client.force_login(platform_admin)
    return client


def test_regular_users_cannot_enter_the_platform(client, member):
    user, _ = member(Role.ADMINISTRACION)
    client.force_login(user)
    assert client.get("/plataforma/").status_code == 403


def test_empty_platform_invites_creating_the_first_client(admin_client):
    body = admin_client.get("/plataforma/").content.decode()
    assert "Aún no hay clientes" in body


def test_create_client_with_generated_slug_and_all_modules(admin_client, platform_admin):
    response = admin_client.post(
        "/plataforma/clientes/nuevo/",
        {
            "name": "Banco Ñandú",
            "slug": "",
            "enabled_modules": list(Module.values),
        },
    )
    client = Client.objects.get()
    assert response.url == "/plataforma/clientes/banco-nandu/"
    assert client.slug == "banco-nandu"
    assert client.is_active
    assert client.created_by == platform_admin
    assert set(client.enabled_modules) == set(Module.values)


def test_reserved_and_duplicate_slugs_are_rejected(admin_client, make_client):
    make_client("acme")
    for slug in ("plataforma", "acme"):
        response = admin_client.post("/plataforma/clientes/nuevo/", {"name": "X", "slug": slug})
        assert response.status_code == 200
    assert Client.objects.count() == 1


def test_edit_modules_and_deactivate_without_changing_slug(admin_client, make_client):
    make_client("acme")
    admin_client.post(
        "/plataforma/clientes/acme/",
        {
            "name": "Acme SA",
            "slug": "otro",
            "enabled_modules": ["matriz", "ruta"],
        },
    )
    client = Client.objects.get()
    assert (client.name, client.slug, client.is_active) == ("Acme SA", "acme", False)
    assert client.enabled_modules == ["matriz", "ruta"]
    assert client.history.count() == 2


def test_invite_new_person_end_to_end(admin_client, make_client, client):
    make_client("acme")
    admin_client.post(
        "/plataforma/clientes/acme/invitar/",
        {"email": "Lucia@Example.com", "role": Role.EQUIPO_CAMBIO},
    )
    assert mail.outbox[-1].to == ["lucia@example.com"]
    link = invite_link()
    assert Invitation.objects.get().token_hash not in link  # only the hash is stored

    client.logout()
    response = client.post(
        link,
        {
            "first_name": "Lucía",
            "last_name": "Pérez",
            "password1": "una-clave-larga-9",
            "password2": "una-clave-larga-9",
        },
    )
    assert response.url == "/c/acme/"
    user = User.objects.get(email="lucia@example.com")
    assert user.memberships.get().role == Role.EQUIPO_CAMBIO
    assert client.get("/c/acme/").status_code == 200

    # The link works once.
    client.logout()
    assert client.get(link).status_code == 410


def test_existing_account_must_log_in_as_the_invitee(admin_client, make_client, make_user, client):
    make_client("acme")
    lucia = make_user("lucia@example.com")
    admin_client.post(
        "/plataforma/clientes/acme/invitar/", {"email": "lucia@example.com", "role": Role.GUIA}
    )
    link = invite_link()

    client.logout()
    assert client.get(link).url.startswith("/entrar/?next=")

    client.force_login(make_user("otra@example.com"))
    assert client.get(link).status_code == 403

    client.force_login(lucia)
    assert client.post(link).url == "/c/acme/"
    assert Membership.objects.get(user=lucia).role == Role.GUIA


def test_reinviting_replaces_the_pending_invitation(admin_client, make_client):
    make_client("acme")
    for role in (Role.GUIA, Role.CAPITAN):
        admin_client.post(
            "/plataforma/clientes/acme/invitar/", {"email": "a@example.com", "role": role}
        )
    assert list(Invitation.objects.pending().values_list("role", flat=True)) == [Role.CAPITAN]


def test_revoked_invitation_no_longer_works(admin_client, make_client, client):
    make_client("acme")
    admin_client.post(
        "/plataforma/clientes/acme/invitar/", {"email": "a@example.com", "role": Role.GUIA}
    )
    link = invite_link()
    inv = Invitation.objects.get()
    admin_client.post(f"/plataforma/clientes/acme/invitaciones/{inv.pk}/anular/")
    client.logout()
    assert client.get(link).status_code == 410


def test_cannot_invite_an_existing_member(admin_client, member):
    member(Role.GUIA, email="ya@example.com")
    response = admin_client.post(
        "/plataforma/clientes/acme/invitar/", {"email": "ya@example.com", "role": Role.CAPITAN}
    )
    assert response.status_code == 400
    assert not mail.outbox


def test_change_role_and_deactivate_member(admin_client, member, client):
    user, _ = member(Role.CAPITAN)
    m = Membership.objects.get()
    url = f"/plataforma/clientes/acme/miembros/{m.pk}/"
    admin_client.post(url, {"role": Role.GUIA})
    admin_client.post(url, {"is_active": "0"})
    m.refresh_from_db()
    assert (m.role, m.is_active) == (Role.GUIA, False)
    assert m.history.count() == 3

    client.force_login(user)
    assert client.get("/c/acme/").status_code == 404


def test_createplatformadmin_promotes_existing_account(make_user):
    user = make_user("yo@example.com")
    call_command("createplatformadmin", email="YO@example.com")
    user.refresh_from_db()
    assert user.is_platform_admin


class TestSystemCatalogAdmin:
    def test_regular_users_cannot_edit_system_catalogs(self, client, member):
        user, _ = member(Role.ADMINISTRACION)
        client.force_login(user)
        assert client.get("/plataforma/catalogos/").status_code == 403

    def test_index_flags_what_is_pending(self, admin_client):
        body = admin_client.get("/plataforma/catalogos/").content.decode()
        assert "Por definir" in body and "Faltan" in body

    def test_add_origin_value_gets_a_stable_code(self, admin_client):
        from apps.catalogs.models import SystemCatalogItem

        for _ in range(2):
            admin_client.post(
                "/plataforma/catalogos/origen/nuevo/",
                {"label": "Diagnóstico inicial", "order": 1, "is_active": "on"},
            )
        codes = SystemCatalogItem.objects.of("origen").values_list("code", flat=True)
        assert sorted(codes) == ["diagnostico_inicial", "diagnostico_inicial_2"]

    def test_edit_label_keeps_code(self, admin_client):
        from apps.catalogs.models import SystemCatalogItem

        item = SystemCatalogItem.objects.get(catalog="tipo_impacto", code="cultura")
        admin_client.post(
            f"/plataforma/catalogos/tipo_impacto/{item.pk}/",
            {
                "label": "Cultura organizacional",
                "help_text": "Ayuda",
                "order": 5,
                "is_active": "on",
            },
        )
        item.refresh_from_db()
        assert (item.code, item.label, item.help_text) == (
            "cultura",
            "Cultura organizacional",
            "Ayuda",
        )

    def test_unknown_catalog_is_404(self, admin_client):
        assert admin_client.get("/plataforma/catalogos/nada/nuevo/").status_code == 404

    def scale_post(self, labels, definitions=("",) * 4, name="Resistencia esperada"):
        data = {"name": name, "help_text": ""}
        for v, (label, definition) in enumerate(zip(labels, definitions, strict=True), 1):
            data[f"nivel{v}-label"] = label
            data[f"nivel{v}-definition"] = definition
        return data

    def test_pending_scale_needs_all_four_levels(self, admin_client):
        from apps.catalogs.models import Scale

        url = "/plataforma/escalas/resistencia/"
        response = admin_client.post(url, self.scale_post(["Baja", "Media", "", ""]))
        assert response.status_code == 200
        assert not Scale.objects.get(code="resistencia").levels.exists()

        admin_client.post(url, self.scale_post(["Baja", "Media", "Alta", "Muy alta"]))
        scale = Scale.objects.get(code="resistencia")
        assert [lvl.label for lvl in scale.levels.all()] == ["Baja", "Media", "Alta", "Muy alta"]

    def test_saving_a_pending_scale_empty_keeps_it_pending(self, admin_client):
        from apps.catalogs.models import Scale

        admin_client.post(
            "/plataforma/escalas/preparacion/",
            self.scale_post([""] * 4, name="Preparación del grupo"),
        )
        assert not Scale.objects.get(code="preparacion").levels.exists()

    def test_add_definitions_to_magnitude(self, admin_client):
        from apps.catalogs.models import Scale

        defs = ["Ajuste menor", "Cambia tareas", "Cambia el rol", "Transforma el trabajo"]
        admin_client.post(
            "/plataforma/escalas/magnitud/",
            self.scale_post(["Leve", "Moderado", "Alto", "Profundo"], defs, name="Magnitud"),
        )
        scale = Scale.objects.get(code="magnitud")
        assert [lvl.definition for lvl in scale.levels.all()] == defs
