"""Questionnaire points and grading. Every questionnaire totals 100 points."""

from decimal import ROUND_DOWN, Decimal

from django.utils.translation import gettext as _

from .models import MAX_OPTIONS, TOTAL_POINTS, TipoPregunta

CENT = Decimal("0.01")


def equal_split(n: int) -> list[Decimal]:
    """100 points over n questions in cents; the leftover cents go to the first ones."""
    if n <= 0:
        return []
    base = (TOTAL_POINTS / n).quantize(CENT, rounding=ROUND_DOWN)
    leftover = int((TOTAL_POINTS - base * n) / CENT)
    return [base + CENT if i < leftover else base for i in range(n)]


def redistribute(cuestionario):
    """Equal split across the questionnaire's questions (draft only)."""
    preguntas = list(cuestionario.preguntas.all())
    for pregunta, puntos in zip(preguntas, equal_split(len(preguntas)), strict=True):
        if pregunta.puntos != puntos:
            pregunta.puntos = puntos
            pregunta.save(update_fields=["puntos"])


def publish_errors(cuestionario):
    """Everything that must be fixed before publishing. Empty list means ready."""
    errors = []
    preguntas = list(cuestionario.preguntas.prefetch_related("opciones"))
    if not preguntas:
        return [_("Agrega al menos una pregunta.")]
    total = sum((p.puntos for p in preguntas), Decimal("0"))
    if total != TOTAL_POINTS:
        errors.append(_("Los puntos suman %(total)s; deben sumar 100.") % {"total": total})
    for i, p in enumerate(preguntas, start=1):
        opciones = list(p.opciones.all())
        correctas = sum(o.correcta for o in opciones)
        if len(opciones) < 2:
            errors.append(_("Pregunta %(n)s: necesita al menos dos opciones.") % {"n": i})
        if len(opciones) > MAX_OPTIONS:
            errors.append(
                _("Pregunta %(n)s: máximo %(max)s opciones.") % {"n": i, "max": MAX_OPTIONS}
            )
        if p.tipo == TipoPregunta.SI_NO and len(opciones) != 2:
            errors.append(_("Pregunta %(n)s: una pregunta Sí o no tiene dos opciones.") % {"n": i})
        if p.tipo == TipoPregunta.MULTIPLE and correctas < 1:
            errors.append(_("Pregunta %(n)s: marca al menos una opción correcta.") % {"n": i})
        if p.tipo != TipoPregunta.MULTIPLE and correctas != 1:
            errors.append(_("Pregunta %(n)s: marca exactamente una opción correcta.") % {"n": i})
        if p.puntos <= 0:
            errors.append(_("Pregunta %(n)s: tiene 0 puntos.") % {"n": i})
    return errors


def grade(cuestionario, elecciones):
    """elecciones: {pregunta_id: set(opcion_id)}. Returns (points per question, total, passed).

    Multiple choice is all-or-nothing: full points only if exactly the correct options are
    marked (the document's working assumption, §7.2)."""
    per_question = {}
    for p in cuestionario.preguntas.prefetch_related("opciones"):
        correctas = {o.pk for o in p.opciones.all() if o.correcta}
        elegidas = set(elecciones.get(p.pk, set()))
        per_question[p.pk] = p.puntos if elegidas == correctas else Decimal("0")
    total = sum(per_question.values(), Decimal("0")).quantize(CENT)
    return per_question, total, total >= cuestionario.nota_minima
