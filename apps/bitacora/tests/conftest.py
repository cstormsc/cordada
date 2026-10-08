import pytest

from apps.catalogs.models import SystemCatalogItem
from apps.core.tenancy import tenant_context


def categoria(code):
    return SystemCatalogItem.objects.get(catalog="categoria_ticket", code=code)


@pytest.fixture
def make_ticket(acme, equipo):
    def make(cat="conocimiento", **kwargs):
        data = {
            "titulo": "No encuentro el botón",
            "descripcion": "d",
            "categoria": categoria(cat),
            "registrado_por": equipo,
        }
        data.update(kwargs)
        with tenant_context(acme):
            from apps.bitacora.models import Ticket

            return Ticket.objects.create(**data)

    return make


@pytest.fixture
def login_as(client, member, acme):
    def login(role, email=None):
        user, _ = member(role, client=acme, email=email or f"{role}@example.com")
        client.force_login(user)
        return user

    return login
