from decimal import Decimal

import pytest

from apps.core.tenancy import tenant_context
from apps.formularios import scoring
from apps.formularios.models import Opcion, Pregunta, TipoPregunta

D = Decimal


@pytest.mark.parametrize(
    ("n", "expected"),
    [
        (1, ["100.00"]),
        (3, ["33.34", "33.33", "33.33"]),
        (4, ["25.00"] * 4),
        (6, ["16.67", "16.67", "16.67", "16.67", "16.66", "16.66"]),
        (7, ["14.29", "14.29", "14.29", "14.29", "14.28", "14.28", "14.28"]),
    ],
)
def test_equal_split_always_totals_100(n, expected):
    split = scoring.equal_split(n)
    assert split == [D(x) for x in expected]
    assert sum(split) == D("100")


@pytest.mark.parametrize("n", range(1, 40))
def test_equal_split_sums_for_any_size(n):
    assert sum(scoring.equal_split(n)) == D("100")


@pytest.mark.django_db
class TestPublishChecks:
    def test_ready(self, make_cuestionario, acme):
        c = make_cuestionario(3)
        with tenant_context(acme):
            assert scoring.publish_errors(c) == []

    def test_points_must_total_100(self, make_cuestionario, acme):
        c = make_cuestionario(2)
        with tenant_context(acme):
            Pregunta.objects.filter(cuestionario=c).update(puntos=D("40"))
            assert "deben sumar 100" in scoring.publish_errors(c)[0]

    def test_option_rules(self, make_cuestionario, acme):
        c = make_cuestionario(0)
        with tenant_context(acme):
            simple = Pregunta.objects.create(cuestionario=c, texto="s", puntos=D("50"))
            Opcion.objects.create(pregunta=simple, texto="a", correcta=True)
            Opcion.objects.create(pregunta=simple, texto="b", correcta=True)
            multiple = Pregunta.objects.create(
                cuestionario=c, texto="m", puntos=D("50"), tipo=TipoPregunta.MULTIPLE
            )
            for t in "abcdef":
                Opcion.objects.create(pregunta=multiple, texto=t)
            errors = " ".join(scoring.publish_errors(c))
        assert "exactamente una opción correcta" in errors
        assert "máximo 5 opciones" in errors
        assert "al menos una opción correcta" in errors

    def test_empty(self, make_cuestionario, acme):
        with tenant_context(acme):
            assert scoring.publish_errors(make_cuestionario(0)) == ["Agrega al menos una pregunta."]


@pytest.mark.django_db
def test_grading_multiple_is_all_or_nothing(make_cuestionario, acme):
    c = make_cuestionario(0, nota_minima=D("80"))
    with tenant_context(acme):
        p1 = Pregunta.objects.create(cuestionario=c, texto="simple", puntos=D("40"))
        a = Opcion.objects.create(pregunta=p1, texto="a", correcta=True)
        Opcion.objects.create(pregunta=p1, texto="b")
        p2 = Pregunta.objects.create(
            cuestionario=c, texto="multi", puntos=D("60"), tipo=TipoPregunta.MULTIPLE
        )
        x = Opcion.objects.create(pregunta=p2, texto="x", correcta=True)
        y = Opcion.objects.create(pregunta=p2, texto="y", correcta=True)
        z = Opcion.objects.create(pregunta=p2, texto="z")
        assert scoring.grade(c, {p1.pk: {a.pk}, p2.pk: {x.pk, y.pk}})[1:] == (D("100.00"), True)
        assert scoring.grade(c, {p1.pk: {a.pk}, p2.pk: {x.pk}})[1:] == (D("40.00"), False)
        assert scoring.grade(c, {p1.pk: {a.pk}, p2.pk: {x.pk, y.pk, z.pk}})[1] == D("40.00")


@pytest.mark.django_db
def test_default_pass_mark_is_80(make_cuestionario):
    assert make_cuestionario().nota_minima == D("80")
