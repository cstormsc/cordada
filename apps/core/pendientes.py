"""«Para ti» on a client's home: what needs this person's attention, by role.

Each count links to the list (with its filter) that shows exactly those items, and only
appears if the person can open that list. «A tu cargo» lists their own impacts and
activities that are overdue or due within a week.
"""

from datetime import timedelta

from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from .models import Module
from .permissions import Action, role_actions

A = Action
SEMANA = 7


def _cuando(fecha, hoy):
    dias = (fecha - hoy).days
    if dias < 0:
        return ngettext("venció hace %(n)s día", "venció hace %(n)s días", -dias) % {"n": -dias}
    if dias == 0:
        return _("vence hoy")
    return ngettext("vence en %(n)s día", "vence en %(n)s días", dias) % {"n": dias}


def para_ti(request):
    client, membership, user = request.client, request.membership, request.user
    hoy = timezone.localdate()
    limite = hoy + timedelta(days=SEMANA)

    def acts(module):
        return role_actions(membership.role, module) if client.has_module(module) else frozenset()

    def url(name, query=""):
        return reverse(name, args=[client.slug]) + (f"?{query}" if query else "")

    items, mios = [], []

    def add(count, singular, plural, href, tono=""):
        if count:
            items.append(
                {"n": count, "texto": ngettext(singular, plural, count), "url": href, "tono": tono}
            )

    # Matriz
    matriz = acts(Module.MATRIZ)
    if A.VIEW in matriz:
        from apps.matriz.models import ACTIVE_STATES, Estado, Impacto, sin_criterio_q

        abiertos = Impacto.objects.exclude(estado__in=[Estado.CERRADO, Estado.DESCARTADO])
        if A.EDIT in matriz:
            add(
                Impacto.objects.filter(estado=Estado.PROPUESTO).count(),
                "propuesta de impacto por validar",
                "propuestas de impacto por validar",
                url("matriz:index", "estado=propuesto"),
                "warn",
            )
            add(
                abiertos.filter(sin_criterio_q(), prioridad=1).count(),
                "impacto P1 sin criterio de cierre",
                "impactos P1 sin criterio de cierre",
                url("matriz:index", "alerta=p1_sin_criterio"),
                "alert",
            )
        add(
            abiertos.filter(severidad=4).count(),
            "impacto con severidad extrema abierto",
            "impactos con severidad extrema abiertos",
            url("matriz:index", "alerta=extrema"),
            "alert",
        )
        if A.EDIT in matriz:
            add(
                Impacto.objects.filter(estado__in=ACTIVE_STATES, actividades__isnull=True)
                .distinct()
                .count(),
                "impacto activo sin actividades en la Ruta",
                "impactos activos sin actividades en la Ruta",
                url("matriz:index", "alerta=descubiertos"),
                "warn",
            )
        for i in (
            abiertos.exclude(estado=Estado.ATENDIDO)
            .filter(responsable=user, fecha_compromiso__lte=limite)
            .order_by("fecha_compromiso")
        ):
            mios.append(
                {
                    "codigo": i.codigo,
                    "titulo": i.titulo,
                    "url": reverse("matriz:detalle", args=[client.slug, i.numero]),
                    "cuando": _cuando(i.fecha_compromiso, hoy),
                    "vencido": i.fecha_compromiso < hoy,
                    "fecha": i.fecha_compromiso,
                }
            )

    # Ruta
    ruta = acts(Module.RUTA)
    if A.VIEW_OWN_GROUP in ruta:
        from apps.ruta.models import DONE, Actividad, Cumplimiento

        visibles = (
            Actividad.objects.all()
            if A.VIEW in ruta
            else Actividad.objects.of_groups(membership.grupos.all())
        )
        if A.EDIT in ruta:
            add(
                Actividad.objects.with_cumplimiento(hoy)
                .filter(cumplimiento=Cumplimiento.NO_REALIZADA)
                .count(),
                "actividad vencida sin realizar",
                "actividades vencidas sin realizar",
                url("ruta:index", "cumplimiento=no_realizada"),
                "alert",
            )
        for a in (
            visibles.filter(responsable=user, no_planificada=False, fecha_planificada__lte=limite)
            .exclude(estado__in=DONE)
            .order_by("fecha_planificada")
        ):
            mios.append(
                {
                    "codigo": a.codigo,
                    "titulo": a.titulo,
                    "url": reverse("ruta:detalle", args=[client.slug, a.numero]),
                    "cuando": _cuando(a.fecha_planificada, hoy),
                    "vencido": a.fecha_planificada < hoy,
                    "fecha": a.fecha_planificada,
                }
            )

    # Bitácora
    bitacora = acts(Module.BITACORA)
    if bitacora:
        from apps.bitacora.models import OPEN_TICKET_STATES, EstadoTicket, Ticket

        E = EstadoTicket
        if A.CLASSIFY in bitacora:
            add(
                Ticket.objects.filter(estado=E.NUEVO).count(),
                "ticket nuevo por clasificar",
                "tickets nuevos por clasificar",
                url("bitacora:index", "estado=nuevo"),
                "warn",
            )
            add(
                Ticket.objects.filter(validado=False)
                .exclude(estado__in=[E.NUEVO, E.EN_CLASIFICACION, E.CERRADO])
                .count(),
                "fallo grave derivado sin validar",
                "fallos graves derivados sin validar",
                url("bitacora:index", "sin_validar=on"),
                "alert",
            )
        if A.EDIT_DERIVED in bitacora:
            add(
                Ticket.objects.filter(estado=E.DERIVADO_TI).count(),
                "ticket esperando en TI",
                "tickets esperando en TI",
                url("bitacora:ti"),
                "warn",
            )
        if A.REGISTER in bitacora and A.VIEW not in bitacora:
            add(
                Ticket.objects.filter(registrado_por=user, estado__in=OPEN_TICKET_STATES).count(),
                "ticket tuyo abierto",
                "tickets tuyos abiertos",
                url("bitacora:index", "estado=abiertos"),
            )

    # Formularios
    formularios = acts(Module.FORMULARIOS)
    if formularios:
        from apps.formularios import certificacion
        from apps.formularios.models import (
            Cuestionario,
            EstadoCertificacion,
            EstadoCuestionario,
            EstadoLista,
            Evaluacion,
            ListaObservacion,
        )

        C = EstadoCertificacion
        if A.LEADER_EVAL in formularios:
            pendientes = 0
            for lista in ListaObservacion.objects.filter(estado=EstadoLista.PUBLICADA):
                equipo = certificacion.team(lista, user.email)
                hechas = lista.evaluaciones.filter(lider=user, persona__in=equipo).exclude(
                    estado=C.PENDIENTE
                )
                pendientes += equipo.count() - hechas.count()
            add(
                pendientes,
                "persona de tu equipo por evaluar",
                "personas de tu equipo por evaluar",
                url("formularios:evaluar_index"),
                "warn",
            )
            add(
                Evaluacion.objects.filter(lider=user, estado=C.APLICADO).count(),
                "evaluación esperando tu resumen firmado",
                "evaluaciones esperando tu resumen firmado",
                url("formularios:evaluar_index"),
            )
        if formularios & {A.EDIT, A.DESIGN}:
            add(
                Evaluacion.objects.filter(estado=C.EN_REFUERZO).count(),
                "persona en refuerzo tras la evaluación práctica",
                "personas en refuerzo tras la evaluación práctica",
                url("formularios:listas"),
                "warn",
            )
            add(
                Cuestionario.objects.filter(estado=EstadoCuestionario.BORRADOR).count(),
                "cuestionario en borrador",
                "cuestionarios en borrador",
                url("formularios:index"),
            )

    # Dashboard: the overall figure, for those who see the dashboard.
    avance = None
    if A.VIEW in acts(Module.DASHBOARD):
        from apps.dashboard import indicators as ind

        avance = next(
            (t for t in ind.tiles(ind.Ctx(client)) if t.indicator.key == ind.GENERAL), None
        )

    mios.sort(key=lambda m: m["fecha"])
    return {"items": items, "mios": mios, "avance": avance, "semana": SEMANA}
