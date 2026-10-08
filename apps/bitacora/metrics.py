"""Bitácora metrics (§6): per 100 people, by type, response times and recurrence."""

from django.db.models import Avg, Count, F, Q

from apps.catalogs.models import GrupoImpactado, SystemCatalog, SystemCatalogItem

from .models import OPEN_TICKET_STATES, Ticket


def _hours(delta):
    return round(delta.total_seconds() / 3600, 1) if delta is not None else None


def metricas(tickets=None, *, desde=None, hasta=None):
    qs = tickets if tickets is not None else Ticket.objects.all()
    if desde:
        qs = qs.filter(created_at__date__gte=desde)
    if hasta:
        qs = qs.filter(created_at__date__lte=hasta)

    times = {
        "primera": Avg(F("primera_respuesta_at") - F("created_at")),
        "resolucion": Avg(F("resuelto_at") - F("created_at")),
    }
    by_cat = {
        row["categoria"]: row
        for row in qs.values("categoria").annotate(
            total=Count("id"),
            abiertos=Count("id", filter=Q(estado__in=OPEN_TICKET_STATES)),
            graves=Count("id", filter=Q(urgencia="grave")),
            **times,
        )
    }
    categorias = []
    for cat in SystemCatalogItem.objects.of(SystemCatalog.CATEGORIA_TICKET):
        row = by_cat.get(cat.pk, {})
        categorias.append(
            {
                "categoria": cat,
                "total": row.get("total", 0),
                "abiertos": row.get("abiertos", 0),
                "graves": row.get("graves", 0),
                "primera_h": _hours(row.get("primera")),
                "resolucion_h": _hours(row.get("resolucion")),
            }
        )

    per_group = {r["grupo"]: r["n"] for r in qs.values("grupo").annotate(n=Count("id"))}
    grupos = []
    for g in GrupoImpactado.objects.all():
        n = per_group.get(g.pk, 0)
        if n or g.is_active:
            grupos.append(
                {
                    "grupo": g,
                    "total": n,
                    "por_100": round(100 * n / g.personas, 1) if g.personas else None,
                }
            )

    total = qs.count()
    recurrentes = qs.filter(recurrente_de__isnull=False).count()
    overall = qs.aggregate(**times)
    return {
        "total": total,
        "abiertos": qs.filter(estado__in=OPEN_TICKET_STATES).count(),
        "sin_grupo": per_group.get(None, 0),
        "primera_h": _hours(overall["primera"]),
        "resolucion_h": _hours(overall["resolucion"]),
        "categorias": categorias,
        "grupos": grupos,
        "recurrentes": recurrentes,
        "pct_recurrentes": round(100 * recurrentes / total) if total else None,
        "mas_repetidos": Ticket.objects.filter(recurrencias__in=qs)
        .annotate(n=Count("recurrencias", distinct=True))
        .order_by("-n", "numero")[:5],
    }
