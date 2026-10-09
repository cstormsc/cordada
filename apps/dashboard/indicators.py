"""Dashboard indicators (Parte B §8).

Each indicator carries what §8 asks for: formula, source, frequency, owner and a
traffic light against thresholds. Thresholds are still to be defined (§13.3): the
defaults here are starting points, editable per client in Configuración → Indicadores.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal

from django.db.models import Count, Exists, OuterRef, Q, Sum
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.bitacora.models import IMPACTO_NO_ANTICIPADO, Ticket
from apps.catalogs.models import GrupoImpactado
from apps.formularios.models import (
    Enlace,
    EstadoCertificacion,
    EstadoCuestionario,
    Evaluacion,
    Respuesta,
)
from apps.formularios.results import suppressed
from apps.matriz.models import ACTIVE_STATES, Estado, Impacto
from apps.ruta.models import DONE, Actividad, Cumplimiento
from apps.scoring.rules import RiskBand

from .models import IndicadorConfig, ValorManual

FRENTES = [
    ("impactos", _("Impactos")),
    ("comunicacion", _("Comunicación")),
    ("movilizacion", _("Movilización")),
    ("formacion", _("Formación")),
    ("transversal", _("Transversales")),
]
NIVELES = {
    "ejecucion": _("Ejecución"),
    "respuesta": _("Respuesta"),
    "adopcion": _("Adopción"),
    "resultados": _("Resultados"),
}

GENERAL = "avance_general"
GENERAL_FRENTES = ("impactos", "comunicacion", "movilizacion", "formacion")

# Impacts that have been validated (no longer just proposals) and were not discarded.
WORKED_STATES = (*ACTIVE_STATES, Estado.ATENDIDO, Estado.CERRADO)
DONE_IMPACT_STATES = (Estado.ATENDIDO, Estado.CERRADO)


@dataclass
class Ctx:
    client: object
    tiempo: object = None
    grupo: object = None
    today: object = None
    min_size: int = 5

    def __post_init__(self):
        self.today = self.today or timezone.localdate()
        self.min_size = self.client.tamano_minimo_grupo

    def impactos(self):
        qs = Impacto.objects.all()
        if self.tiempo:
            qs = qs.filter(tiempo=self.tiempo)
        if self.grupo:
            qs = qs.filter(grupo=self.grupo)
        return qs

    def actividades(self, frente=None):
        qs = Actividad.objects.with_cumplimiento(self.today)
        if frente:
            qs = qs.filter(frente__code=frente)
        if self.tiempo:
            qs = qs.filter(tiempo=self.tiempo)
        if self.grupo:
            qs = qs.filter(grupos=self.grupo).distinct()
        return qs

    def tickets(self):
        qs = Ticket.objects.all()
        if self.grupo:
            qs = qs.filter(grupo=self.grupo)
        return qs

    def grupos(self):
        qs = GrupoImpactado.objects.filter(is_active=True)
        return qs.filter(pk=self.grupo.pk) if self.grupo else qs


@dataclass
class Result:
    value: Decimal | None = None
    detail: str = ""

    @property
    def has_value(self):
        return self.value is not None


def _pct(part, whole):
    return Decimal(round(100 * part / whole)) if whole else None


@dataclass
class Indicator:
    key: str
    frente: str
    nivel: str
    nombre: str
    formula: str
    fuente: str
    unit: str = "%"  # "%", "n" or "pts"
    higher_is_better: bool | None = True  # None: informative, no traffic light
    verde: Decimal | None = None
    amarillo: Decimal | None = None
    frecuencia: str = _("Semanal")
    compute: Callable | None = None
    manual: bool = False
    provisional: bool = False
    extra: dict = field(default_factory=dict)


# --- calculations ---


def imp_con_plan(ctx):
    base = ctx.impactos().filter(estado__in=WORKED_STATES)
    total = base.count()
    ok = base.filter(responsable__isnull=False, actividades__isnull=False).distinct().count()
    return Result(_pct(ok, total), _("%(ok)s de %(n)s impactos") % {"ok": ok, "n": total})


def imp_criticos(ctx):
    criticos = (
        ctx.impactos().filter(riesgo_nivel=RiskBand.CRITICO).exclude(estado=Estado.DESCARTADO)
    )
    total = criticos.count()
    mitigados = criticos.filter(estado__in=DONE_IMPACT_STATES).count()
    return Result(
        _pct(mitigados, total),
        _("%(a)s abiertos · %(m)s mitigados") % {"a": total - mitigados, "m": mitigados},
    )


def imp_no_anticipados(ctx):
    tickets = ctx.tickets().filter(categoria__code=IMPACTO_NO_ANTICIPADO)
    n = tickets.count()
    llevados = tickets.filter(impacto__isnull=False).count()
    return Result(Decimal(n), _("%(l)s llevados a la matriz") % {"l": llevados})


def _cumplimiento(ctx, frente):
    acts = ctx.actividades(frente)
    counts = {
        r["cumplimiento"]: r["n"]
        for r in acts.values("cumplimiento").annotate(n=Count("id", distinct=True))
    }
    a = counts.get(Cumplimiento.A_TIEMPO, 0)
    r = counts.get(Cumplimiento.CON_RETRASO, 0)
    nr = counts.get(Cumplimiento.NO_REALIZADA, 0)
    return a, r, nr


def com_a_tiempo(ctx):
    a, r, nr = _cumplimiento(ctx, "comunicacion")
    due = a + r + nr
    return Result(
        _pct(a, due),
        _("%(a)s de %(d)s vencidos · %(r)s con retraso · %(nr)s no realizados")
        % {"a": a, "d": due, "r": r, "nr": nr},
    )


def com_cobertura(ctx):
    grupos = ctx.grupos()
    total = grupos.count()
    done = ctx.actividades("comunicacion").filter(estado__in=DONE)
    cubiertos = grupos.filter(actividades__in=done).distinct().count()
    return Result(
        _pct(cubiertos, total),
        _("%(c)s de %(n)s grupos con una comunicación realizada") % {"c": cubiertos, "n": total},
    )


def com_iniciativa(ctx):
    n = ctx.actividades("comunicacion").filter(no_planificada=True).count()
    return Result(Decimal(n), _("comunicaciones no planificadas registradas"))


def mov_participacion(ctx):
    a, r, nr = _cumplimiento(ctx, "movilizacion")
    due = a + r + nr
    return Result(
        _pct(a + r, due),
        _("%(h)s de %(d)s actividades vencidas realizadas") % {"h": a + r, "d": due},
    )


def mov_tickets(ctx):
    personas = ctx.grupos().filter(personas__isnull=False).aggregate(s=Sum("personas"))["s"]
    tickets = ctx.tickets()
    if not personas:
        return Result(None, _("Indica el número de personas de cada grupo en Configuración."))
    n = tickets.filter(grupo__in=ctx.grupos().filter(personas__isnull=False)).count()
    abiertos = tickets.exclude(estado__in=["resuelto", "cerrado"]).count()
    return Result(
        Decimal(round(100 * n / personas, 1)),
        _("%(n)s tickets · %(a)s abiertos") % {"n": n, "a": abiertos},
    )


def for_asignada(ctx):
    base = ctx.impactos().filter(requiere_formacion=True, estado__in=WORKED_STATES)
    total = base.count()
    ok = base.filter(actividades__frente__code="formacion").distinct().count()
    return Result(
        _pct(ok, total),
        _("%(ok)s de %(n)s impactos que requieren formación") % {"ok": ok, "n": total},
    )


def _verification(ctx, all_groups=False):
    """(invited, respondents, passed) per group across published questionnaires."""
    enlaces = Enlace.objects.filter(
        cuestionario__estado__in=[EstadoCuestionario.PUBLICADO, EstadoCuestionario.CERRADO]
    ).annotate(
        respondio=Exists(Respuesta.objects.filter(enlace=OuterRef("pk"))),
        aprobo=Exists(Respuesta.objects.filter(enlace=OuterRef("pk"), aprobado=True)),
    )
    if ctx.tiempo:
        enlaces = enlaces.filter(cuestionario__impacto__tiempo=ctx.tiempo)
    if ctx.grupo and not all_groups:
        enlaces = enlaces.filter(persona__grupo=ctx.grupo)
    return enlaces.values("persona__grupo").annotate(
        invitados=Count("id"),
        respondieron=Count("id", filter=Q(respondio=True)),
        aprobados=Count("id", filter=Q(aprobo=True)),
    )


def _hidden(rows, count, ctx):
    """Groups whose figures can't be shown (see formularios.results.suppressed)."""
    return suppressed({r["persona__grupo"]: r[count] for r in rows}, ctx.min_size)


def _too_few(ctx):
    return Result(
        None,
        _("Muy pocas respuestas para mostrarlo (mínimo %(m)s por grupo).") % {"m": ctx.min_size},
    )


def for_verificacion(ctx):
    rows = list(_verification(ctx))
    inv = sum(r["invitados"] for r in rows)
    resp = sum(r["respondieron"] for r in rows)
    apr = sum(r["aprobados"] for r in rows)
    if resp < ctx.min_size:
        return _too_few(ctx)
    if ctx.grupo and ctx.grupo.pk in _hidden(
        _verification(ctx, all_groups=True), "respondieron", ctx
    ):
        return _too_few(ctx)
    return Result(
        _pct(apr, inv),
        _("%(a)s aprobados de %(i)s con enlace · %(r)s respondieron")
        % {"a": apr, "i": inv, "r": resp},
    )


def _certification(ctx, all_groups=False):
    evs = Evaluacion.objects.filter(
        estado__in=[EstadoCertificacion.CERTIFICADO, EstadoCertificacion.EN_REFUERZO]
    )
    if ctx.tiempo:
        evs = evs.filter(lista__impacto__tiempo=ctx.tiempo)
    if ctx.grupo and not all_groups:
        evs = evs.filter(persona__grupo=ctx.grupo)
    return evs.values("persona__grupo").annotate(
        evaluados=Count("id"),
        certificados=Count("id", filter=Q(estado=EstadoCertificacion.CERTIFICADO)),
    )


def for_certificacion(ctx):
    rows = list(_certification(ctx))
    ev = sum(r["evaluados"] for r in rows)
    cert = sum(r["certificados"] for r in rows)
    if ev < ctx.min_size:
        return _too_few(ctx)
    if ctx.grupo and ctx.grupo.pk in _hidden(
        _certification(ctx, all_groups=True), "evaluados", ctx
    ):
        return _too_few(ctx)
    return Result(
        _pct(cert, ev),
        _("%(c)s certificados de %(e)s evaluados · %(r)s en refuerzo")
        % {"c": cert, "e": ev, "r": ev - cert},
    )


def readiness_by_group(ctx):
    """Provisional readiness index per group: average of the components with data.
    Its real definition is pending (§13.2-13.3)."""
    imp = {
        r["grupo"]: r
        for r in ctx.impactos()
        .filter(estado__in=WORKED_STATES)
        .values("grupo")
        .annotate(total=Count("id"), hechos=Count("id", filter=Q(estado__in=DONE_IMPACT_STATES)))
    }
    ver_rows, cert_rows = list(_verification(ctx)), list(_certification(ctx))
    ver = {r["persona__grupo"]: r for r in ver_rows}
    cert = {r["persona__grupo"]: r for r in cert_rows}
    ver_hidden = _hidden(_verification(ctx, all_groups=True), "respondieron", ctx)
    cert_hidden = _hidden(_certification(ctx, all_groups=True), "evaluados", ctx)
    rows = []
    for g in ctx.grupos().order_by("name"):
        parts = {}
        if (r := imp.get(g.pk)) and r["total"]:
            parts["impactos"] = _pct(r["hechos"], r["total"])
        if (r := ver.get(g.pk)) and r["respondieron"] and g.pk not in ver_hidden:
            parts["verificacion"] = _pct(r["aprobados"], r["invitados"])
        if (r := cert.get(g.pk)) and r["evaluados"] and g.pk not in cert_hidden:
            parts["certificacion"] = _pct(r["certificados"], r["evaluados"])
        value = Decimal(round(sum(parts.values()) / len(parts))) if parts else None
        rows.append({"grupo": g, "value": value, "parts": parts})
    return rows


def tr_preparacion(ctx):
    rows = [r for r in readiness_by_group(ctx) if r["value"] is not None]
    if not rows:
        return Result(None, _("Sin datos todavía"))
    avg = Decimal(round(sum(r["value"] for r in rows) / len(rows)))
    return Result(avg, _("promedio de %(n)s grupos con datos") % {"n": len(rows)})


def manual(ctx, key):
    qs = ValorManual.objects.filter(key=key)
    qs = qs.filter(grupo=ctx.grupo) if ctx.grupo else qs.filter(grupo__isnull=True)
    last = qs.order_by("-fecha", "-created_at").first()
    if last is None:
        return Result(None, _("Sin datos cargados"))
    return Result(last.valor, _("dato del %(f)s") % {"f": last.fecha.strftime("%d/%m/%Y")})


D = Decimal
PLAT = _("Plataforma")
MANUAL = _("Carga manual")

INDICATORS = [
    Indicator(
        GENERAL,
        "general",
        "resultados",
        _("Avance general del proyecto"),
        _(
            "Promedio de los cuatro frentes (Impactos, Comunicación, Movilización, Formación). "
            "Cada frente es el promedio de sus indicadores en % que tienen datos."
        ),
        _("Dashboard"),
        verde=D(80),
        amarillo=D(60),
        frecuencia=_("Por etapa"),
        provisional=True,
    ),
    Indicator(
        "imp_con_plan",
        "impactos",
        "ejecucion",
        _("Impactos con plan y responsable"),
        _(
            "Impactos validados (no propuestos ni descartados) con responsable y al menos una "
            "actividad en la Ruta ÷ impactos validados."
        ),
        _("Matriz y Ruta"),
        verde=D(90),
        amarillo=D(70),
        compute=imp_con_plan,
    ),
    Indicator(
        "imp_criticos",
        "impactos",
        "resultados",
        _("Críticos mitigados"),
        _(
            "Impactos con nivel de riesgo Crítico atendidos o cerrados ÷ impactos críticos no "
            "descartados."
        ),
        _("Matriz"),
        verde=D(80),
        amarillo=D(50),
        compute=imp_criticos,
    ),
    Indicator(
        "imp_no_anticipados",
        "impactos",
        "respuesta",
        _("Impactos no anticipados"),
        _("Tickets de la Bitácora con categoría «impacto no anticipado»."),
        _("Bitácora"),
        unit="n",
        higher_is_better=None,
        compute=imp_no_anticipados,
    ),
    Indicator(
        "com_a_tiempo",
        "comunicacion",
        "ejecucion",
        _("Mensajes a tiempo"),
        _("Comunicaciones hechas a tiempo ÷ comunicaciones planificadas cuya fecha ya pasó."),
        _("Ruta"),
        verde=D(90),
        amarillo=D(75),
        compute=com_a_tiempo,
    ),
    Indicator(
        "com_cobertura",
        "comunicacion",
        "ejecucion",
        _("Cobertura de grupos"),
        _("Grupos con al menos una comunicación completada ÷ grupos activos."),
        _("Ruta"),
        verde=D(90),
        amarillo=D(70),
        compute=com_cobertura,
    ),
    Indicator(
        "com_iniciativa",
        "comunicacion",
        "respuesta",
        _("Eventos detectados por iniciativa propia"),
        _("Comunicaciones registradas como no planificadas (surgieron sobre la marcha)."),
        _("Ruta"),
        unit="n",
        higher_is_better=None,
        compute=com_iniciativa,
    ),
    Indicator(
        "mov_participacion",
        "movilizacion",
        "respuesta",
        _("Participación"),
        _(
            "Actividades de movilización realizadas (a tiempo o con retraso) ÷ actividades de "
            "movilización planificadas cuya fecha ya pasó."
        ),
        _("Ruta"),
        verde=D(80),
        amarillo=D(60),
        compute=mov_participacion,
    ),
    Indicator(
        "mov_comprension",
        "movilizacion",
        "adopcion",
        _("Comprensión del cambio"),
        _("Porcentaje de personas que declaran entender el cambio (encuesta)."),
        MANUAL,
        verde=D(80),
        amarillo=D(60),
        manual=True,
    ),
    Indicator(
        "mov_tickets",
        "movilizacion",
        "respuesta",
        _("Tickets por cada 100 personas"),
        _("Tickets de grupos con número de personas definido × 100 ÷ personas de esos grupos."),
        _("Bitácora"),
        unit="n",
        higher_is_better=False,
        compute=mov_tickets,
    ),
    Indicator(
        "for_asignada",
        "formacion",
        "ejecucion",
        _("Impactos con formación asignada"),
        _(
            "Impactos que requieren formación y tienen una actividad del frente Formación ÷ "
            "impactos validados que requieren formación."
        ),
        _("Matriz y Ruta"),
        verde=D(90),
        amarillo=D(70),
        compute=for_asignada,
    ),
    Indicator(
        "for_personas",
        "formacion",
        "ejecucion",
        _("Personas formadas antes de la salida"),
        _(
            "Personas que completaron la formación antes de la salida ÷ personas que debían "
            "formarse."
        ),
        MANUAL,
        verde=D(90),
        amarillo=D(75),
        manual=True,
    ),
    Indicator(
        "for_verificacion",
        "formacion",
        "resultados",
        _("Verificación de competencia"),
        _(
            "Personas que aprobaron un cuestionario ÷ personas con enlace (cuestionarios "
            "publicados)."
        ),
        _("Formularios"),
        verde=D(80),
        amarillo=D(60),
        compute=for_verificacion,
    ),
    Indicator(
        "for_certificacion",
        "formacion",
        "resultados",
        _("Certificación del líder"),
        _("Personas certificadas ÷ personas evaluadas por su líder."),
        _("Formularios"),
        verde=D(80),
        amarillo=D(60),
        compute=for_certificacion,
    ),
    Indicator(
        "tr_usuarios_activos",
        "transversal",
        "adopcion",
        _("Usuarios activos"),
        _("Usuarios activos del sistema nuevo ÷ usuarios esperados."),
        MANUAL,
        verde=D(80),
        amarillo=D(60),
        manual=True,
    ),
    Indicator(
        "tr_adopcion_30",
        "transversal",
        "adopcion",
        _("Adopción sostenida a 30 días"),
        _("Usuarios que siguen activos 30 días después de la salida ÷ usuarios esperados."),
        MANUAL,
        verde=D(80),
        amarillo=D(60),
        manual=True,
        frecuencia=_("Mensual"),
    ),
    Indicator(
        "tr_adopcion_60",
        "transversal",
        "adopcion",
        _("Adopción sostenida a 60 días"),
        _("Igual, a 60 días."),
        MANUAL,
        verde=D(80),
        amarillo=D(60),
        manual=True,
        frecuencia=_("Mensual"),
    ),
    Indicator(
        "tr_adopcion_90",
        "transversal",
        "adopcion",
        _("Adopción sostenida a 90 días"),
        _("Igual, a 90 días."),
        MANUAL,
        verde=D(80),
        amarillo=D(60),
        manual=True,
        frecuencia=_("Mensual"),
    ),
    Indicator(
        "tr_preparacion",
        "transversal",
        "resultados",
        _("Índice de preparación"),
        _(
            "Provisional: promedio por grupo de los componentes con datos (impactos "
            "atendidos, verificación aprobada, certificación), y promedio entre grupos."
        ),
        _("Matriz y Formularios"),
        unit="pts",
        verde=D(70),
        amarillo=D(50),
        compute=tr_preparacion,
        provisional=True,
    ),
    Indicator(
        "tr_diagnostico",
        "transversal",
        "resultados",
        _("Diagnóstico: cambio respecto del inicio"),
        _("Puntaje del diagnóstico actual menos puntaje del diagnóstico inicial."),
        MANUAL,
        unit="pts",
        higher_is_better=None,
        manual=True,
        frecuencia=_("Por etapa"),
    ),
]
BY_KEY = {i.key: i for i in INDICATORS}


@dataclass
class Tile:
    indicator: Indicator
    result: Result
    verde: Decimal | None
    amarillo: Decimal | None
    responsable: str
    frecuencia: str
    partes: list = field(default_factory=list)  # avance general: one row per front

    @property
    def status(self):
        v, ind = self.result.value, self.indicator
        if v is None or ind.higher_is_better is None or self.verde is None:
            return "none"
        amarillo = self.amarillo if self.amarillo is not None else self.verde
        if ind.higher_is_better:
            return "good" if v >= self.verde else "warning" if v >= amarillo else "critical"
        return "good" if v <= self.verde else "warning" if v <= amarillo else "critical"


def configs():
    return {c.key: c for c in IndicadorConfig.objects.all()}


def tiles(ctx):
    cfg = configs()
    out = []
    for ind in INDICATORS:
        c = cfg.get(ind.key)
        if c is not None and not c.activo:
            continue
        if ind.key == GENERAL:
            result = Result()  # filled in below, from the other tiles
        else:
            result = manual(ctx, ind.key) if ind.manual else ind.compute(ctx)
        out.append(
            Tile(
                ind,
                result,
                verde=c.verde if c else ind.verde,
                amarillo=c.amarillo if c else ind.amarillo,
                responsable=c.responsable if c and c.responsable else "",
                frecuencia=c.frecuencia if c and c.frecuencia else ind.frecuencia,
            )
        )
    for tile in out:
        if tile.indicator.key == GENERAL:
            tile.result, tile.partes = avance_general(out)
    return out


def avance_general(tiles):
    """Provisional overall figure: average of the four fronts, each the average of its
    percentage indicators with data (higher is better). Fronts without data are left out."""
    nombres = dict(FRENTES)
    partes = []
    for code in GENERAL_FRENTES:
        values = [
            t.result.value
            for t in tiles
            if t.indicator.frente == code
            and t.indicator.unit == "%"
            and t.indicator.higher_is_better
            and t.result.value is not None
        ]
        score = Decimal(round(sum(values) / len(values))) if values else None
        partes.append({"code": code, "nombre": nombres[code], "valor": score, "n": len(values)})
    with_data = [p["valor"] for p in partes if p["valor"] is not None]
    if not with_data:
        return Result(None, _("Sin datos todavía")), partes
    value = Decimal(round(sum(with_data) / len(with_data)))
    detail = _("promedio de %(n)s de 4 frentes con datos") % {"n": len(with_data)}
    return Result(value, detail), partes


def threshold(key):
    c = configs().get(key)
    return c.verde if c else BY_KEY[key].verde, (c.amarillo if c else BY_KEY[key].amarillo)


def alerts(ctx):
    """§8: P1 without closing criterion, Extrema severity, groups below readiness threshold."""
    from apps.matriz.models import sin_criterio_q
    from apps.scoring.rules import EXTREME_SEVERITY, Priority

    open_impacts = ctx.impactos().exclude(estado__in=[Estado.CERRADO, Estado.DESCARTADO])
    _verde, amarillo = threshold("tr_preparacion")
    limit = amarillo if amarillo is not None else _verde
    bajo = [
        r
        for r in readiness_by_group(ctx)
        if limit is not None and r["value"] is not None and r["value"] < limit
    ]
    return {
        "p1_sin_criterio": open_impacts.filter(sin_criterio_q(), prioridad=Priority.P1).order_by(
            "numero"
        ),
        "extrema": open_impacts.filter(severidad=EXTREME_SEVERITY).order_by("numero"),
        "grupos_bajo_umbral": bajo,
        "umbral_preparacion": limit,
    }


def tickets_by_type(ctx):
    from apps.catalogs.models import SystemCatalog, SystemCatalogItem

    counts = {
        r["categoria"]: r["n"] for r in ctx.tickets().values("categoria").annotate(n=Count("id"))
    }
    return [
        {"label": str(c), "value": counts.get(c.pk, 0)}
        for c in SystemCatalogItem.objects.of(SystemCatalog.CATEGORIA_TICKET)
    ]


__all__ = [
    "Ctx",
    "INDICATORS",
    "BY_KEY",
    "FRENTES",
    "NIVELES",
    "tiles",
    "alerts",
    "readiness_by_group",
    "tickets_by_type",
]
