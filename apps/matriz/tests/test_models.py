import pytest

from apps.core.tenancy import tenant_context
from apps.matriz import workflow
from apps.matriz.models import Estado, Impacto, Transicion
from apps.scoring.rules import Priority, RiskBand

pytestmark = pytest.mark.django_db


def test_numbers_are_consecutive_per_client(make_impacto, make_client, equipo):
    a1, a2 = make_impacto(), make_impacto()
    with tenant_context(make_client("globex")):
        g1 = Impacto.objects.create(titulo="x", descripcion="y", registrado_por=equipo)
    assert (a1.numero, a2.numero, g1.numero) == (1, 2, 1)
    assert a2.codigo == "IMP-002"


def test_risk_and_priority_are_calculated_on_save(make_impacto):
    impacto = make_impacto(magnitud=4, probabilidad=4, severidad=3)
    assert impacto.riesgo_puntaje == 12
    assert impacto.riesgo_nivel == RiskBand.CRITICO
    assert impacto.prioridad_calculada == impacto.prioridad == Priority.P1


def test_priority_needs_all_three_inputs(make_impacto):
    impacto = make_impacto(magnitud=4, probabilidad=2)
    assert impacto.riesgo_nivel is None and impacto.prioridad is None


def test_manual_override_wins_and_can_be_cleared(make_impacto, acme):
    impacto = make_impacto(magnitud=1, probabilidad=1, severidad=1)
    assert impacto.prioridad == Priority.P4
    with tenant_context(acme):
        impacto.prioridad_ajustada = Priority.P2
        impacto.save()
        assert impacto.prioridad == Priority.P2 and impacto.prioridad_calculada == Priority.P4
        impacto.prioridad_ajustada = None
        impacto.save()
        assert impacto.prioridad == Priority.P4


def test_alerts(make_impacto):
    assert make_impacto(severidad=4).alerta_severidad
    assert make_impacto(magnitud=4, probabilidad=4, severidad=4).alerta_p1_sin_criterio
    assert not make_impacto(complete=True, magnitud=4, probabilidad=4,
                            severidad=4).alerta_p1_sin_criterio


class TestWorkflow:
    def test_cannot_evaluate_with_missing_fields(self, make_impacto, acme, equipo):
        impacto = make_impacto()
        with tenant_context(acme), pytest.raises(workflow.TransitionError) as e:
            workflow.transition(impacto, Estado.EVALUADO, user=equipo)
        assert "criterio" in str(e.value)
        assert impacto.estado == Estado.PROPUESTO

    def test_full_lifecycle_records_each_step(self, make_impacto, acme, equipo):
        impacto = make_impacto(complete=True)
        with tenant_context(acme):
            for target in (Estado.EVALUADO, Estado.EN_ATENCION, Estado.ATENDIDO, Estado.CERRADO):
                workflow.transition(impacto, target, user=equipo)
            workflow.transition(impacto, Estado.REABIERTO, user=equipo, reason="Volvió a fallar")
            workflow.transition(impacto, Estado.EN_ATENCION, user=equipo)
            steps = list(Transicion.objects.values_list("desde", "hacia"))
        assert steps[0] == ("propuesto", "evaluado")
        assert steps[-2:] == [("cerrado", "reabierto"), ("reabierto", "en_atencion")]
        impacto.refresh_from_db()
        assert impacto.estado == Estado.EN_ATENCION

    def test_discard_and_reopen_need_a_reason(self, make_impacto, acme, equipo):
        impacto = make_impacto()
        with tenant_context(acme):
            with pytest.raises(workflow.TransitionError):
                workflow.transition(impacto, Estado.DESCARTADO, user=equipo, reason="  ")
            workflow.transition(impacto, Estado.DESCARTADO, user=equipo, reason="Duplicado")
            assert impacto.is_locked

    def test_disallowed_jumps(self, make_impacto, acme, equipo):
        impacto = make_impacto(complete=True)
        with tenant_context(acme):
            for target in (Estado.CERRADO, Estado.ATENDIDO, "inventado", None):
                with pytest.raises(workflow.TransitionError):
                    workflow.transition(impacto, target, user=equipo)

    def test_every_state_has_a_way_forward(self):
        assert set(workflow.TRANSITIONS) == set(Estado)

    def test_required_fields_exist_on_the_model(self):
        for name in workflow.REQUIRED_FOR_EVALUATION:
            Impacto._meta.get_field(name)
