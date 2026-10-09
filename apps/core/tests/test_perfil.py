import pytest

from apps.catalogs.models import Cargo, UnidadOrganizacional
from apps.core.models import Membership, Role, User
from apps.core.tenancy import tenant_context

pytestmark = pytest.mark.django_db
URL = "/perfil/"


def test_requires_login(client):
    assert client.get(URL).url.startswith("/entrar/")


def test_header_links_to_the_profile(client, member):
    user, _ = member(Role.GUIA)
    user.first_name, user.last_name = "Ana", "Pérez"
    user.save()
    client.force_login(user)
    body = client.get("/c/acme/").content.decode()
    assert f'href="{URL}"' in body and "Ana Pérez" in body


def test_edit_name_but_not_email_or_privileges(client, make_user):
    user = make_user("ana@example.com")
    client.force_login(user)
    client.post(
        URL,
        {
            "accion": "datos",
            "first_name": "  Ana María ",
            "last_name": "Pérez",
            "email": "otra@example.com",
            "is_platform_admin": "on",
            "is_staff": "on",
        },
    )
    user.refresh_from_db()
    assert (user.first_name, user.last_name) == ("Ana María", "Pérez")
    assert user.email == "ana@example.com"
    assert not user.is_platform_admin and not user.is_staff

    response = client.post(URL, {"accion": "datos", "first_name": "", "last_name": "Pérez"})
    assert response.status_code == 200 and "obligatorio" in response.content.decode()


def test_shows_own_spaces_with_position(client, member, make_client):
    user, acme = member(Role.CAPITAN)
    with tenant_context(acme):
        cargo = Cargo.objects.create(name="Supervisor")
        depto = UnidadOrganizacional.objects.create(kind="departamento", name="Operaciones")
    Membership.objects.filter(user=user).update(cargo=cargo, departamento=depto)
    otro, _ = member(Role.GUIA, client=make_client("globex"), email="otro@example.com")
    client.force_login(user)
    body = client.get(URL).content.decode()
    assert "Supervisor · Operaciones" in body and "Capitán" in body
    assert "globex" not in body.lower()


def test_change_password_and_stay_logged_in(client, make_user):
    user = make_user("ana@example.com")
    client.force_login(user)
    wrong = client.post(
        URL,
        {
            "accion": "clave",
            "old_password": "no-es",
            "new_password1": "otra-clave-larga-7",
            "new_password2": "otra-clave-larga-7",
        },
    )
    assert wrong.status_code == 200
    user.refresh_from_db()
    assert user.check_password("clave-segura-123")

    client.post(
        URL,
        {
            "accion": "clave",
            "old_password": "clave-segura-123",
            "new_password1": "otra-clave-larga-7",
            "new_password2": "otra-clave-larga-7",
        },
    )
    user.refresh_from_db()
    assert user.check_password("otra-clave-larga-7")
    assert client.get(URL).status_code == 200  # session kept
    assert User.objects.get(pk=user.pk).email == "ana@example.com"
