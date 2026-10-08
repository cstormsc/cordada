import pytest

from apps.core.models import Role
from apps.core.tenancy import NoCurrentClient, get_current_client, tenant_context
from apps.core.tests.tenantapp.models import Note

pytestmark = pytest.mark.django_db


def test_query_without_current_client_raises():
    with pytest.raises(NoCurrentClient):
        list(Note.objects.all())


def test_queries_only_see_the_current_client(make_client):
    acme, globex = make_client("acme"), make_client("globex")
    with tenant_context(acme):
        Note.objects.create(text="de acme")
    with tenant_context(globex):
        Note.objects.create(text="de globex")
        assert list(Note.objects.values_list("text", flat=True)) == ["de globex"]
        assert not Note.objects.filter(text="de acme").exists()
    assert Note.unscoped.count() == 2


def test_save_assigns_current_client(make_client):
    acme = make_client("acme")
    with tenant_context(acme):
        note = Note.objects.create(text="x")
    assert note.client == acme


def test_cannot_save_a_row_into_another_client(make_client):
    acme, globex = make_client("acme"), make_client("globex")
    with tenant_context(acme):
        note = Note.objects.create(text="x")
    with tenant_context(globex), pytest.raises(NoCurrentClient):
        note.text = "cambiado"
        note.save()


def test_tenant_context_is_restored(make_client):
    with tenant_context(make_client()):
        pass
    assert get_current_client() is None


class TestClientUrls:
    def test_anonymous_is_sent_to_login(self, client, make_client):
        make_client("acme")
        response = client.get("/c/acme/")
        assert response.status_code == 302
        assert response.url.startswith("/entrar/")

    def test_member_gets_in(self, client, member):
        user, _ = member(Role.CAPITAN)
        client.force_login(user)
        response = client.get("/c/acme/")
        assert response.status_code == 200
        assert get_current_client() is None  # reset after the request

    def test_non_member_gets_404(self, client, member, make_user, make_client):
        member(Role.EQUIPO_CAMBIO, client=make_client("globex"))
        user, _ = member(Role.EQUIPO_CAMBIO, email="otro@example.com")
        client.force_login(user)
        assert client.get("/c/globex/").status_code == 404

    def test_inactive_membership_gets_404(self, client, member):
        user, _ = member(Role.EQUIPO_CAMBIO, is_active=False)
        client.force_login(user)
        assert client.get("/c/acme/").status_code == 404

    def test_inactive_client_gets_404(self, client, member, make_client):
        user, _ = member(Role.EQUIPO_CAMBIO, client=make_client("acme", is_active=False))
        client.force_login(user)
        assert client.get("/c/acme/").status_code == 404

    def test_home_lists_only_visible_modules(self, client, member):
        user, _ = member(Role.LIDER_AREA)
        client.force_login(user)
        body = client.get("/c/acme/").content.decode()
        assert "Formularios" in body and "Guía de campo" in body
        assert "Matriz de Impactos" not in body
