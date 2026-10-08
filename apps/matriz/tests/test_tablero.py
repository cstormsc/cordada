import datetime
import re

import pytest

from apps.core.models import Role
from apps.matriz.models import Estado, Transicion

pytestmark = pytest.mark.django_db

URL = "/c/acme/matriz/tablero/"


def column(body, estado):
    """HTML of one board column."""
    match = re.search(rf'<section class="kcol[^"]*" data-estado="{estado}".*?</section>', body,
                      re.S)
    return match.group(0)


def test_cards_land_in_their_state_column(client, equipo, make_impacto):
    make_impacto(titulo="Uno propuesto")
    make_impacto(complete=True, titulo="Uno en atención", estado=Estado.EN_ATENCION)
    client.force_login(equipo)
    body = client.get(URL).content.decode()
    assert "Uno propuesto" in column(body, "propuesto")
    assert "Uno en atención" in column(body, "en_atencion")
    assert "Uno en atención" not in column(body, "propuesto")
    assert 'class="container wide"' in body  # all columns fit on a laptop screen


def test_editor_cards_carry_allowed_moves(client, equipo, make_impacto):
    make_impacto(estado=Estado.ATENDIDO)
    client.force_login(equipo)
    body = client.get(URL).content.decode()
    assert 'data-editable="1"' in body
    assert 'data-allowed="cerrado,reabierto"' in body
    assert 'data-needs-reason="reabierto"' in body


def test_board_flags(client, equipo, make_impacto):
    make_impacto(complete=True, estado=Estado.EVALUADO, severidad=4,
                 fecha_compromiso=datetime.date(2020, 1, 1))
    client.force_login(equipo)
    card = column(client.get(URL).content.decode(), "evaluado")
    assert "Extrema" in card and "Descubierto" in card and "overdue" in card


def test_filters_apply_to_the_board(client, equipo, make_impacto):
    make_impacto(titulo="Coincide")
    make_impacto(titulo="Otro")
    client.force_login(equipo)
    body = client.get(f"{URL}?q=coinc").content.decode()
    assert "Coincide" in body and "Otro" not in body


def test_htmx_refresh_returns_only_the_board(client, equipo):
    client.force_login(equipo)
    body = client.get(URL, HTTP_HX_REQUEST="true").content.decode()
    assert body.lstrip().startswith('<div id="board"')


def test_sponsor_sees_a_read_only_board(client, member, acme, make_impacto):
    impacto = make_impacto(complete=True)
    sponsor, _ = member(Role.PATROCINADOR, client=acme, email="pmo@example.com")
    client.force_login(sponsor)
    body = client.get(URL).content.decode()
    assert "data-editable" not in body and "data-allowed" not in body
    response = client.post(f"/c/acme/matriz/{impacto.numero}/mover/", {"hacia": "evaluado"})
    assert response.status_code == 403
    impacto.refresh_from_db()
    assert impacto.estado == Estado.PROPUESTO


@pytest.mark.parametrize("role", [Role.CAPITAN, Role.LIDER_AREA])
def test_roles_without_matrix_view(client, member, acme, role):
    user, _ = member(role, client=acme, email="x@example.com")
    client.force_login(user)
    assert client.get(URL).status_code == 403


class TestMove:
    def url(self, impacto):
        return f"/c/acme/matriz/{impacto.numero}/mover/"

    def test_valid_move(self, client, equipo, make_impacto):
        impacto = make_impacto(complete=True)
        client.force_login(equipo)
        data = client.post(self.url(impacto), {"hacia": "evaluado"}).json()
        assert data == {"ok": True, "message": "IMP-001: Evaluado.", "warning": None}
        impacto.refresh_from_db()
        assert impacto.estado == Estado.EVALUADO

    def test_missing_fields_are_reported(self, client, equipo, make_impacto):
        impacto = make_impacto()
        client.force_login(equipo)
        response = client.post(self.url(impacto), {"hacia": "evaluado"})
        assert response.status_code == 400
        assert "Faltan campos" in response.json()["errors"][0]

    def test_reason_is_required_and_recorded(self, client, equipo, make_impacto, acme):
        impacto = make_impacto()
        client.force_login(equipo)
        assert client.post(self.url(impacto), {"hacia": "descartado"}).status_code == 400
        client.post(self.url(impacto), {"hacia": "descartado", "motivo": "Duplicado de IMP-002"})
        impacto.refresh_from_db()
        assert impacto.estado == Estado.DESCARTADO
        from apps.core.tenancy import tenant_context
        with tenant_context(acme):
            assert Transicion.objects.get().motivo == "Duplicado de IMP-002"

    def test_disallowed_move(self, client, equipo, make_impacto):
        impacto = make_impacto()
        client.force_login(equipo)
        assert client.post(self.url(impacto), {"hacia": "cerrado"}).status_code == 400

    def test_requires_post(self, client, equipo, make_impacto):
        impacto = make_impacto()
        client.force_login(equipo)
        assert client.get(self.url(impacto)).status_code == 405
