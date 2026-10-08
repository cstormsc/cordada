import pytest

from apps.bitacora import workflow
from apps.bitacora.models import EstadoTicket as E
from apps.bitacora.models import TicketTransicion, Urgencia
from apps.core.models import Module, Role
from apps.core.permissions import role_actions
from apps.core.tenancy import tenant_context

pytestmark = pytest.mark.django_db


def acts(role):
    return role_actions(role, Module.BITACORA)


GUIA, TECNICO, CAPITAN = acts(Role.GUIA), acts(Role.EQUIPO_TECNICO), acts(Role.CAPITAN)


def go(ticket, target, user, actions, reason=""):
    return workflow.transition(ticket, target, user=user, actions=actions, reason=reason)


def test_technical_ticket_full_path_records_times(make_ticket, acme, equipo):
    t = make_ticket("tecnico")
    with tenant_context(acme):
        go(t, E.EN_CLASIFICACION, equipo, GUIA)
        assert t.primera_respuesta_at is not None
        go(t, E.VALIDADO, equipo, GUIA)
        assert t.validado and t.validado_por == equipo
        go(t, E.DERIVADO_TI, equipo, GUIA)
        go(t, E.RESUELTO, equipo, TECNICO)
        assert t.resuelto_at is not None
        go(t, E.CERRADO, equipo, GUIA)
        assert t.cerrado_at is not None
        assert TicketTransicion.objects.count() == 5


def test_only_technical_tickets_go_to_it(make_ticket, acme, equipo):
    t = make_ticket("conocimiento", estado=E.VALIDADO)
    with tenant_context(acme):
        with pytest.raises(workflow.TicketError, match="categoría técnica"):
            go(t, E.DERIVADO_TI, equipo, GUIA)
        go(t, E.RESUELTO, equipo, GUIA)  # knowledge: solved by the guides


def test_technical_tickets_are_not_resolved_without_it(make_ticket, acme, equipo):
    t = make_ticket("tecnico", estado=E.VALIDADO)
    with tenant_context(acme), pytest.raises(workflow.TicketError, match="TI"):
        go(t, E.RESUELTO, equipo, GUIA)


def test_severe_failure_goes_straight_to_it_and_is_validated_in_parallel(make_ticket, acme,
                                                                         equipo):
    t = make_ticket("tecnico", urgencia=Urgencia.GRAVE)
    with tenant_context(acme):
        go(t, E.DERIVADO_TI, equipo, CAPITAN)  # the captain who registered it
        assert t.estado == E.DERIVADO_TI and not t.validado
        assert workflow.can_validate(t, GUIA) and not workflow.can_validate(t, CAPITAN)
        workflow.validate(t, user=equipo, actions=GUIA)
        assert t.validado and t.estado == E.DERIVADO_TI


@pytest.mark.parametrize(("cat", "urgencia"), [("tecnico", "normal"), ("conocimiento", "grave")])
def test_shortcut_only_for_severe_technical(make_ticket, acme, equipo, cat, urgencia):
    t = make_ticket(cat, urgencia=urgencia)
    with tenant_context(acme), pytest.raises(workflow.TicketError):
        go(t, E.DERIVADO_TI, equipo, CAPITAN)


def test_it_returns_misclassified_ticket_with_reason(make_ticket, acme, equipo):
    t = make_ticket("tecnico", estado=E.DERIVADO_TI, validado=True)
    with tenant_context(acme):
        with pytest.raises(workflow.TicketError, match="motivo"):
            go(t, E.EN_CLASIFICACION, equipo, TECNICO)
        go(t, E.EN_CLASIFICACION, equipo, TECNICO, reason="Es de capacitación")
        assert t.estado == E.EN_CLASIFICACION and not t.validado


def test_reopen_clears_resolution(make_ticket, acme, equipo):
    t = make_ticket("conocimiento", estado=E.VALIDADO)
    with tenant_context(acme):
        go(t, E.RESUELTO, equipo, GUIA)
        go(t, E.VALIDADO, equipo, GUIA, reason="Volvió a pasar")
        assert t.resuelto_at is None


@pytest.mark.parametrize(("estado", "actions", "expected"), [
    (E.NUEVO, CAPITAN, [E.DERIVADO_TI]),
    (E.NUEVO, GUIA, [E.EN_CLASIFICACION, E.DERIVADO_TI]),
    (E.NUEVO, TECNICO, []),
    (E.DERIVADO_TI, GUIA, []),
    (E.DERIVADO_TI, TECNICO, [E.RESUELTO, E.EN_CLASIFICACION]),
    (E.RESUELTO, TECNICO, []),
    (E.CERRADO, GUIA, []),
])
def test_who_can_take_each_step(make_ticket, estado, actions, expected):
    t = make_ticket("tecnico", estado=estado)
    assert [s.target for s in workflow.available(t, actions)] == expected


def test_every_state_is_covered():
    assert set(workflow.STEPS) == set(E)
