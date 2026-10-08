import datetime

import pytest

from apps.catalogs.models import GrupoImpactado, SystemCatalogItem
from apps.core.models import Client, Membership, Role, User
from apps.core.tenancy import tenant_context


@pytest.fixture
def make_user(db):
    def make(email="persona@example.com", **kwargs):
        return User.objects.create_user(email=email, password="clave-segura-123", **kwargs)

    return make


@pytest.fixture
def platform_admin(make_user):
    return make_user("admin@cordada.local", is_platform_admin=True)


@pytest.fixture
def make_client(db):
    def make(slug="acme", **kwargs):
        return Client.objects.create(name=kwargs.pop("name", slug.title()), slug=slug, **kwargs)

    return make


@pytest.fixture
def member(make_user, make_client):
    """Returns a factory: member(role, client=None, email=...) -> (user, client)."""

    def make(role=Role.EQUIPO_CAMBIO, client=None, email="miembro@example.com", **kwargs):
        client = client or make_client()
        user = make_user(email)
        Membership.objects.create(user=user, client=client, role=role, **kwargs)
        return user, client

    return make


def _item(catalog, code):
    return SystemCatalogItem.objects.get(catalog=catalog, code=code)


@pytest.fixture
def acme(make_client):
    return make_client("acme")


@pytest.fixture
def equipo(member, acme):
    user, _ = member(Role.EQUIPO_CAMBIO, client=acme, email="equipo@example.com")
    return user


@pytest.fixture
def grupo(acme):
    with tenant_context(acme):
        return GrupoImpactado.objects.create(name="Cobranzas")


@pytest.fixture
def make_impacto(acme, equipo):
    def make(complete=False, **kwargs):
        with tenant_context(acme):
            return _make(complete, **kwargs)

    def _make(complete, **kwargs):
        data = {"titulo": "Nuevo flujo de cobranza", "descripcion": "Cambia el proceso",
                "registrado_por": equipo}
        if complete:
            data.update(
                tipo=_item("tipo_impacto", "proceso"),
                grupo=GrupoImpactado.objects.get_or_create(name="Cobranzas")[0],
                magnitud=3, probabilidad=3, severidad=3,
                requiere_comunicacion=True, requiere_movilizacion=False,
                requiere_formacion=True, responsable=equipo,
                fecha_compromiso=datetime.date(2026, 12, 1),
                criterio_evidencia=_item("evidencia_cierre", "formacion_completada"),
                criterio_meta=90, criterio_descripcion="90 % del grupo formado",
            )
        data.update(kwargs)
        from apps.matriz.models import Impacto

        return Impacto.objects.create(**data)

    return make
