"""Leader certification (§7.5): team selection, applying results and the signed summary."""

from django.core.mail import send_mail
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from apps.core.models import Membership, Role

from .models import (
    EstadoCertificacion,
    EstadoCuestionario,
    Evaluacion,
    Persona,
    Respuesta,
)

E = EstadoCertificacion


def team(lista, leader_email):
    """People who report to this leader and should be evaluated for the list's impact.

    If the impact has published questionnaires, only those who passed one of them
    (§7.5, proposal); otherwise the people of the impact's group."""
    impacto = lista.impacto
    personas = Persona.objects.filter(is_active=True, supervisor__iexact=leader_email)
    cuestionarios = impacto.cuestionarios.exclude(estado=EstadoCuestionario.BORRADOR)
    if cuestionarios.exists():
        passed = Respuesta.objects.filter(enlace__cuestionario__in=cuestionarios, aprobado=True)
        personas = personas.filter(enlaces__respuestas__in=passed).distinct()
    elif impacto.grupo_id:
        personas = personas.filter(grupo_id=impacto.grupo_id)
    return personas.order_by("nombre", "email")


def evaluations_for(lista, leader):
    """Ensures one Evaluacion per team member and returns them."""
    personas = list(team(lista, leader.email))
    existing = {e.persona_id: e for e in lista.evaluaciones.filter(persona__in=personas)}
    with transaction.atomic():
        for p in personas:
            if p.pk not in existing:
                existing[p.pk] = Evaluacion.objects.create(lista=lista, persona=p, lider=leader)
    return [existing[p.pk] for p in personas]


EDITABLE = (E.PENDIENTE, E.APLICADO, E.EN_REFUERZO)


def save_results(evaluacion, resultados, observaciones, criterio_ids):
    """Merges {criterio_id: bool} into the saved results (observaciones=None keeps them).
    Complete → aplicado, waiting for the signed summary."""
    if evaluacion.estado not in EDITABLE:
        return False
    evaluacion.resultados = {**evaluacion.resultados, **{str(k): v for k, v in resultados.items()}}
    if observaciones is not None:
        evaluacion.observaciones = observaciones
    complete = all(str(cid) in evaluacion.resultados for cid in criterio_ids)
    if complete:
        evaluacion.estado, evaluacion.aplicada_at = E.APLICADO, timezone.now()
    elif evaluacion.estado == E.APLICADO:
        evaluacion.estado = E.PENDIENTE
    evaluacion.save()
    return True


@transaction.atomic
def register_signed_summary(lista, leader, form, *, notify_request=None):
    """Upload of the signed PDF: every applied evaluation of this leader becomes
    certificado (all criteria met) or en refuerzo."""
    acta = form.save_for(leader, lista=lista, lider=leader)
    criterio_ids = list(lista.criterios.values_list("pk", flat=True))
    refuerzo = []
    for ev in lista.evaluaciones.filter(lider=leader, estado=E.APLICADO).select_related("persona"):
        ev.estado = E.CERTIFICADO if ev.cumple_todo(criterio_ids) else E.EN_REFUERZO
        ev.acta = acta
        ev.save()
        if ev.estado == E.EN_REFUERZO:
            refuerzo.append(ev.persona)
    if refuerzo and notify_request is not None:
        transaction.on_commit(lambda: notify_guides(notify_request, lista, refuerzo))
    return acta, refuerzo


def notify_guides(request, lista, personas):
    """'El refuerzo activa al guía': email the guides of those groups (or all guides)."""
    grupos = {p.grupo_id for p in personas if p.grupo_id}
    guides = Membership.objects.filter(client=lista.client, role=Role.GUIA, is_active=True)
    targeted = guides.filter(grupos__in=grupos).distinct() if grupos else guides.none()
    emails = sorted(
        {m.user.email for m in (targeted if targeted.exists() else guides).select_related("user")}
    )
    if not emails:
        return
    body = render_to_string(
        "formularios/email/refuerzo.txt",
        {
            "lista": lista,
            "personas": personas,
            "client": lista.client,
            "url": request.build_absolute_uri(
                f"/c/{lista.client.slug}/formularios/listas/{lista.pk}/seguimiento/"
            ),
        },
    )
    send_mail(f"Refuerzo · {lista.impacto.codigo} · {lista.client.name}", body, None, emails)


def summary(lista):
    counts = dict.fromkeys(E.values, 0)
    for estado in lista.evaluaciones.values_list("estado", flat=True):
        counts[estado] += 1
    counts["evaluados"] = counts[E.CERTIFICADO] + counts[E.EN_REFUERZO]
    return counts
