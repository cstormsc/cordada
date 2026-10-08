"""Compliance report for stage sessions and the monthly sponsor summary (§5)."""

import calendar

from django.db.models import Count, Q

from apps.catalogs.models import SystemCatalog, SystemCatalogItem
from apps.matriz.models import ACTIVE_STATES, Impacto

from .models import Cumplimiento

C = Cumplimiento


def descubiertos(impactos=None):
    """Active impacts with no activity in the Ruta."""
    impactos = impactos if impactos is not None else Impacto.objects.all()
    return impactos.filter(estado__in=ACTIVE_STATES, actividades__isnull=True)


def month_range(first_day):
    last = calendar.monthrange(first_day.year, first_day.month)[1]
    return first_day, first_day.replace(day=last)


def _pct(part, whole):
    return round(100 * part / whole) if whole else None


def _summary(counts):
    due = counts[C.A_TIEMPO] + counts[C.CON_RETRASO] + counts[C.NO_REALIZADA]
    return {
        **{c.value: counts[c] for c in C},
        "planificadas": sum(counts[c] for c in C if c != C.NO_PLANIFICADA),
        "vencidas": due,
        "pct_a_tiempo": _pct(counts[C.A_TIEMPO], due),
        "pct_realizadas": _pct(counts[C.A_TIEMPO] + counts[C.CON_RETRASO], due),
    }


def informe(actividades, *, tiempo=None, mes=None, frente=None, today=None):
    qs = actividades.with_cumplimiento(today)
    impactos = Impacto.objects.all()
    if tiempo:
        qs = qs.filter(tiempo=tiempo)
        impactos = impactos.filter(tiempo=tiempo)
    if mes:
        start, end = month_range(mes)
        qs = qs.filter(Q(no_planificada=False, fecha_planificada__range=(start, end))
                       | Q(no_planificada=True, fecha_real__range=(start, end)))
    if frente:
        qs = qs.filter(frente=frente)

    by_frente = {
        (row["frente"], row["cumplimiento"]): row["n"]
        for row in qs.values("frente", "cumplimiento").annotate(n=Count("id", distinct=True))
    }
    frentes = SystemCatalogItem.objects.of(SystemCatalog.FRENTE)
    if frente:
        frentes = frentes.filter(pk=frente.pk)
    rows = []
    totals = dict.fromkeys(C, 0)
    for f in frentes:
        counts = {c: by_frente.get((f.pk, c.value), 0) for c in C}
        for c in C:
            totals[c] += counts[c]
        rows.append({"frente": f, **_summary(counts)})

    detail = qs.select_related("responsable", "frente").order_by("fecha_planificada", "numero")
    return {
        "rows": rows,
        "total": _summary(totals),
        "no_realizadas": detail.filter(cumplimiento=C.NO_REALIZADA),
        "con_retraso": detail.filter(cumplimiento=C.CON_RETRASO),
        "no_planificadas": detail.filter(cumplimiento=C.NO_PLANIFICADA),
        "huerfanas": qs.huerfanas().count(),
        "descubiertos": descubiertos(impactos).order_by("prioridad", "numero"),
    }
