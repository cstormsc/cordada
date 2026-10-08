"""Questionnaire results. Individual detail is for the change team only; everything else is
aggregated and hides groups smaller than the client's minimum size (§7.4)."""

from collections import defaultdict
from decimal import Decimal

from .models import Enlace, Respuesta


def best_by_enlace(cuestionario):
    """{enlace_id: (best score, passed, attempts, last date)}."""
    rows = Respuesta.objects.filter(enlace__cuestionario=cuestionario).values(
        "enlace_id", "puntaje", "aprobado", "enviada_at"
    )
    best = {}
    for r in rows:
        prev = best.get(r["enlace_id"])
        attempts = (prev[2] if prev else 0) + 1
        last = max(prev[3], r["enviada_at"]) if prev else r["enviada_at"]
        if prev is None or r["puntaje"] > prev[0]:
            best[r["enlace_id"]] = (r["puntaje"], r["aprobado"], attempts, last)
        else:
            best[r["enlace_id"]] = (prev[0], prev[1], attempts, last)
    return best


def individual(cuestionario):
    best = best_by_enlace(cuestionario)
    rows = []
    for e in cuestionario.enlaces.select_related("persona", "persona__grupo").order_by(
        "persona__nombre", "persona__email"
    ):
        score, passed, attempts, last = best.get(e.pk, (None, None, 0, None))
        rows.append(
            {
                "persona": e.persona,
                "puntaje": score,
                "aprobado": passed,
                "intentos": attempts,
                "ultima": last,
            }
        )
    return rows


def aggregate(cuestionario, *, by="grupo", min_size=5):
    best = best_by_enlace(cuestionario)
    buckets = defaultdict(
        lambda: {"invitados": 0, "respondieron": 0, "aprobados": 0, "suma": Decimal("0")}
    )
    for e in cuestionario.enlaces.select_related("persona", "persona__grupo"):
        value = getattr(e.persona, by)
        key = str(value) if value else ""
        b = buckets[key]
        b["invitados"] += 1
        if e.pk in best:
            score, passed, *_ = best[e.pk]
            b["respondieron"] += 1
            b["aprobados"] += int(passed)
            b["suma"] += score
    rows = []
    for key in sorted(buckets, key=lambda k: (k == "", k.lower())):
        b = buckets[key]
        visible = b["respondieron"] >= min_size
        rows.append(
            {
                "nombre": key,
                "invitados": b["invitados"],
                "respondieron": b["respondieron"],
                "visible": visible,
                "aprobados": b["aprobados"] if visible else None,
                "pct_aprobados": round(100 * b["aprobados"] / b["respondieron"])
                if visible
                else None,
                "promedio": round(b["suma"] / b["respondieron"], 1) if visible else None,
            }
        )
    return rows


def totals(cuestionario):
    best = best_by_enlace(cuestionario)
    invitados = cuestionario.enlaces.count()
    respondieron = len(best)
    aprobados = sum(1 for v in best.values() if v[1])
    return {
        "invitados": invitados,
        "respondieron": respondieron,
        "aprobados": aprobados,
        "pct_respuesta": round(100 * respondieron / invitados) if invitados else None,
        "pct_aprobados": round(100 * aprobados / respondieron) if respondieron else None,
    }


def per_question(cuestionario, *, min_size=5):
    """% of respondents (best attempt) who got each question right."""
    respuestas = Respuesta.objects.filter(enlace__cuestionario=cuestionario)
    best = {}
    for r in respuestas.order_by("enlace_id", "-puntaje", "-enviada_at"):
        best.setdefault(r.enlace_id, r)
    n = len(best)
    rows = []
    for p in cuestionario.preguntas.all():
        right = sum(
            1 for r in best.values() if Decimal(r.puntos_por_pregunta.get(str(p.pk), "0")) > 0
        )
        rows.append({"pregunta": p, "pct": round(100 * right / n) if n >= min_size else None})
    return rows


def for_impacto(impacto, *, min_size=5):
    """Verification of the impact's group across its questionnaires (feeds closing criterion)."""
    rows = []
    for c in impacto.cuestionarios.exclude(estado="borrador"):
        enlaces = Enlace.objects.filter(cuestionario=c)
        if impacto.grupo_id:
            enlaces = enlaces.filter(persona__grupo_id=impacto.grupo_id)
        best = best_by_enlace(c)
        ids = set(enlaces.values_list("pk", flat=True))
        answered = [best[i] for i in ids if i in best]
        visible = len(answered) >= min_size
        rows.append(
            {
                "cuestionario": c,
                "invitados": len(ids),
                "respondieron": len(answered),
                "aprobados": sum(1 for a in answered if a[1]) if visible else None,
                "pct_aprobados": round(100 * sum(1 for a in answered if a[1]) / len(answered))
                if visible
                else None,
                "pct_sobre_invitados": round(100 * sum(1 for a in answered if a[1]) / len(ids))
                if visible and ids
                else None,
            }
        )
    return rows
