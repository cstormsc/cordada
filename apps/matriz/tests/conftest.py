import datetime

import pytest

from apps.catalogs.models import GrupoImpactado, SystemCatalogItem
from apps.core.models import Role
from apps.core.tenancy import tenant_context
from apps.matriz.models import Impacto


def item(catalog, code):
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
                tipo=item("tipo_impacto", "proceso"),
                grupo=GrupoImpactado.objects.get_or_create(name="Cobranzas")[0],
                magnitud=3, probabilidad=3, severidad=3,
                requiere_comunicacion=True, requiere_movilizacion=False,
                requiere_formacion=True, responsable=equipo,
                fecha_compromiso=datetime.date(2026, 12, 1),
                criterio_evidencia=item("evidencia_cierre", "formacion_completada"),
                criterio_meta=90, criterio_descripcion="90 % del grupo formado",
            )
        data.update(kwargs)
        return Impacto.objects.create(**data)

    return make
