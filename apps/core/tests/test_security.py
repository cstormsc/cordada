import pytest
from django.core.cache import cache

from apps.core.login_throttle import MAX_PER_ACCOUNT, MAX_PER_ADDRESS
from apps.matriz.export import safe_cell

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def clean_cache():
    cache.clear()
    yield
    cache.clear()


def login(client, email, password, ip="10.0.0.1"):
    return client.post("/entrar/", {"username": email, "password": password}, REMOTE_ADDR=ip)


class TestLoginThrottling:
    def test_account_is_blocked_after_repeated_failures(self, client, make_user):
        make_user("ana@example.com")
        for _ in range(MAX_PER_ACCOUNT):
            assert (
                "Correo o contraseña incorrectos"
                in login(client, "ana@example.com", "mala").content.decode()
            )
        # Now even the right password is refused, from any address, without checking it.
        blocked = login(client, "ANA@example.com", "clave-segura-123", ip="10.0.0.2")
        assert blocked.status_code == 200 and "Demasiados intentos" in blocked.content.decode()
        cache.clear()  # the window passes
        assert login(client, "ana@example.com", "clave-segura-123").status_code == 302

    def test_success_resets_the_account_count(self, client, make_user):
        make_user("ana@example.com")
        for _ in range(MAX_PER_ACCOUNT - 1):
            login(client, "ana@example.com", "mala")
        assert login(client, "ana@example.com", "clave-segura-123").status_code == 302
        client.logout()
        login(client, "ana@example.com", "mala")
        assert login(client, "ana@example.com", "clave-segura-123").status_code == 302

    def test_one_address_trying_many_accounts_is_blocked(self, client, make_user):
        make_user("ana@example.com")
        for i in range(MAX_PER_ADDRESS):
            login(client, f"nadie{i}@example.com", "mala")
        body = login(client, "ana@example.com", "clave-segura-123").content.decode()
        assert "Demasiados intentos" in body
        assert (
            login(client, "ana@example.com", "clave-segura-123", ip="10.0.0.9").status_code == 302
        )


def test_help_text_is_escaped(client, platform_admin):
    client.force_login(platform_admin)
    body = client.get("/plataforma/clientes/nuevo/").content.decode()
    assert "/c/&lt;identificador&gt;/" in body  # shown as text, not dropped as a tag


@pytest.mark.parametrize("value", ["=1+1", "+1", "-1", "@SUM(A1)", "\t=1", "\r=1"])
def test_formula_like_cells_are_neutralised(value):
    assert safe_cell(value) == "'" + value
