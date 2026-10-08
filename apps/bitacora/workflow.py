"""Ticket flow (Parte B §6). Each step names the permission it needs."""

from collections.abc import Callable
from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.permissions import Action

from .models import EstadoTicket, Ticket, TicketTransicion, Urgencia

E = EstadoTicket
A = Action


def _grave_tecnico(t: Ticket):
    if not (t.urgencia == Urgencia.GRAVE and t.es_tecnico):
        return _("Solo un fallo grave de categoría técnica se deriva sin validar antes.")
    return None


def _tecnico(t: Ticket):
    return None if t.es_tecnico else _("Solo los tickets de categoría técnica se derivan a TI.")


def _no_tecnico(t: Ticket):
    return _("Un ticket técnico lo resuelve TI: derívalo.") if t.es_tecnico else None


@dataclass(frozen=True)
class Step:
    target: EstadoTicket
    label: str
    action: Action
    needs_reason: bool = False
    guard: Callable | None = None


STEPS: dict[EstadoTicket, list[Step]] = {
    E.NUEVO: [
        Step(E.EN_CLASIFICACION, _("Tomar para clasificar"), A.CLASSIFY),
        Step(E.DERIVADO_TI, _("Fallo grave: derivar a TI ya"), A.REGISTER, guard=_grave_tecnico),
    ],
    E.EN_CLASIFICACION: [
        Step(E.VALIDADO, _("Validar clasificación"), A.CLASSIFY),
    ],
    E.VALIDADO: [
        Step(E.DERIVADO_TI, _("Derivar a TI"), A.CLASSIFY, guard=_tecnico),
        Step(E.RESUELTO, _("Marcar resuelto"), A.CLASSIFY, guard=_no_tecnico),
    ],
    E.DERIVADO_TI: [
        Step(E.RESUELTO, _("Marcar resuelto"), A.EDIT_DERIVED),
        Step(E.EN_CLASIFICACION, _("Devolver: mal clasificado"), A.EDIT_DERIVED,
             needs_reason=True),
    ],
    E.RESUELTO: [
        Step(E.CERRADO, _("Cerrar"), A.CLASSIFY),
        Step(E.VALIDADO, _("Reabrir: no quedó resuelto"), A.CLASSIFY, needs_reason=True),
    ],
    E.CERRADO: [],
}


class TicketError(Exception):
    def __init__(self, messages):
        self.messages = [str(m) for m in messages]
        super().__init__("; ".join(self.messages))


def available(ticket, actions):
    """Steps this user (with these Bitácora actions) can take now; guards are not applied,
    so the button shows and explains why when it can't be done."""
    return [s for s in STEPS.get(ticket.estado, []) if s.action in actions]


def can_validate(ticket, actions):
    """Parallel validation of a severe failure sent straight to IT."""
    return (A.CLASSIFY in actions and not ticket.validado
            and ticket.estado in (E.DERIVADO_TI, E.RESUELTO))


@transaction.atomic
def transition(ticket, target, *, user, actions, reason=""):
    steps = {s.target: s for s in available(ticket, actions)}
    if target not in steps:
        raise TicketError([_("Ese cambio de estado no está permitido para tu rol.")])
    step = steps[target]
    errors = []
    if step.guard and (msg := step.guard(ticket)):
        errors.append(msg)
    if step.needs_reason and not reason.strip():
        errors.append(_("Indica el motivo."))
    if errors:
        raise TicketError(errors)

    now = timezone.now()
    TicketTransicion.objects.create(ticket=ticket, desde=ticket.estado, hacia=target,
                                    motivo=reason.strip(), usuario=user)
    if ticket.estado == E.NUEVO and ticket.primera_respuesta_at is None:
        ticket.primera_respuesta_at = now
    if target == E.VALIDADO and ticket.estado == E.EN_CLASIFICACION:
        ticket.validado, ticket.validado_por = True, user
    if target == E.EN_CLASIFICACION and ticket.estado == E.DERIVADO_TI:
        ticket.validado, ticket.validado_por = False, None  # returned by IT: reclassify
    if target == E.RESUELTO:
        ticket.resuelto_at = now
    if target == E.CERRADO:
        ticket.cerrado_at = now
    if ticket.estado == E.RESUELTO and target == E.VALIDADO:
        ticket.resuelto_at = None
    ticket.estado = target
    ticket.save()
    return ticket


def validate(ticket, *, user, actions):
    if not can_validate(ticket, actions):
        raise TicketError([_("No hay nada que validar.")])
    ticket.validado, ticket.validado_por = True, user
    ticket.save(update_fields=["validado", "validado_por"])
    return ticket
