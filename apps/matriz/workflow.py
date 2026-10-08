"""Impact lifecycle (Parte B §4)."""

from dataclasses import dataclass

from django.db import transaction
from django.utils.translation import gettext_lazy as _

from .models import Estado, Impacto, Transicion

E = Estado

# Fields that must be filled before an impact leaves Propuesto. §4 suggests this
# list; the final one is still to be decided (§13.1), so it lives here only.
REQUIRED_FOR_EVALUATION = [
    "titulo",
    "tipo",
    "grupo",
    "magnitud",
    "requiere_comunicacion",
    "requiere_movilizacion",
    "requiere_formacion",
    "responsable",
    "fecha_compromiso",
    "criterio_evidencia",
    "criterio_descripcion",
]


@dataclass(frozen=True)
class Transition:
    target: Estado
    label: str
    needs_reason: bool = False
    check_required: bool = False


TRANSITIONS: dict[Estado, list[Transition]] = {
    E.PROPUESTO: [
        Transition(E.EVALUADO, _("Validar y evaluar"), check_required=True),
        Transition(E.DESCARTADO, _("Descartar"), needs_reason=True),
    ],
    E.EVALUADO: [
        Transition(E.EN_ATENCION, _("Iniciar atención"), check_required=True),
        Transition(E.DESCARTADO, _("Descartar"), needs_reason=True),
    ],
    E.EN_ATENCION: [
        Transition(
            E.ATENDIDO, _("Marcar atendido (cumple el criterio de cierre)"), check_required=True
        ),
        Transition(E.DESCARTADO, _("Descartar"), needs_reason=True),
    ],
    E.ATENDIDO: [
        Transition(E.CERRADO, _("Cerrar")),
        Transition(E.REABIERTO, _("Reabrir"), needs_reason=True),
    ],
    E.CERRADO: [
        Transition(E.REABIERTO, _("Reabrir"), needs_reason=True),
    ],
    E.DESCARTADO: [
        Transition(E.REABIERTO, _("Reabrir"), needs_reason=True),
    ],
    E.REABIERTO: [
        Transition(E.EVALUADO, _("Volver a evaluar"), check_required=True),
        Transition(E.EN_ATENCION, _("Retomar la atención"), check_required=True),
        Transition(E.DESCARTADO, _("Descartar"), needs_reason=True),
    ],
}


class TransitionError(Exception):
    def __init__(self, messages):
        self.messages = messages
        super().__init__("; ".join(str(m) for m in messages))


def available(impacto):
    return TRANSITIONS.get(impacto.estado, [])


def missing_fields(impacto):
    """Verbose names of required fields that are still empty."""
    missing = []
    for name in REQUIRED_FOR_EVALUATION:
        field = Impacto._meta.get_field(name)
        value = getattr(impacto, field.attname)
        if value is None or value == "":
            missing.append(field.verbose_name)
    return missing


@transaction.atomic
def transition(impacto, target, *, user, reason=""):
    allowed = {t.target: t for t in available(impacto)}
    if target not in allowed:
        raise TransitionError([_("Ese cambio de estado no está permitido.")])
    t = allowed[target]
    errors = []
    if t.check_required:
        missing = missing_fields(impacto)
        if missing:
            errors.append(
                _("Faltan campos: %(campos)s.") % {"campos": ", ".join(str(m) for m in missing)}
            )
    if t.needs_reason and not reason.strip():
        errors.append(_("Indica el motivo."))
    if errors:
        raise TransitionError(errors)

    Transicion.objects.create(
        impacto=impacto, desde=impacto.estado, hacia=target, motivo=reason.strip(), usuario=user
    )
    impacto.estado = target
    impacto.save()
    return impacto
