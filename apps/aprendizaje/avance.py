"""A person's progress in a course: lessons seen, completion, their cordada and badges."""

from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.formularios.models import Respuesta

from .models import Ajustes, EstadoCurso, Inscripcion


def cordada_de(persona):
    """The rope team a person climbs with: their branch, else department, else office,
    else impacted group. None when the people list says nothing about it."""
    for valor in (persona.sucursal, persona.departamento, persona.oficina):
        if valor.strip():
            return valor.strip()
    return persona.grupo.name if persona.grupo_id else None


def _aprobada(inscripcion):
    """The person's first passing answer to the course's evaluation, or None."""
    return (
        Respuesta.objects.filter(
            enlace__cuestionario=inscripcion.curso.evaluacion_id,
            enlace__persona=inscripcion.persona_id,
            aprobado=True,
        )
        .order_by("enviada_at")
        .first()
    )


def sincronizar(inscripcion, vistas=None):
    """Sets completada_at once the course counts as complete: the evaluation passed, or,
    without one, every required lesson seen. Returns the inscripcion."""
    if inscripcion.completada_at:
        return inscripcion
    curso = inscripcion.curso
    if curso.evaluacion_id:
        respuesta = _aprobada(inscripcion)
        cuando = respuesta.enviada_at if respuesta else None
    else:
        if vistas is None:
            vistas = set(inscripcion.vistas.values_list("leccion_id", flat=True))
        obligatorias = set(curso.lecciones.filter(obligatoria=True).values_list("pk", flat=True))
        cuando = timezone.now() if obligatorias and obligatorias <= vistas else None
    if cuando:
        inscripcion.completada_at = cuando
        inscripcion.save(update_fields=["completada_at"])
    return inscripcion


def en_plazo(inscripcion):
    fecha = inscripcion.curso.fecha_limite
    return bool(inscripcion.completada_at) and (
        fecha is None or timezone.localdate(inscripcion.completada_at) <= fecha
    )


def cordada(inscripcion):
    """The person's rope team in this course: how many reached the summit in time, and
    whether the team did (the share the client set). None without a team."""
    nombre = cordada_de(inscripcion.persona)
    if nombre is None:
        return None
    equipo = [
        i
        for i in Inscripcion.objects.filter(curso=inscripcion.curso, persona__is_active=True)
        .select_related("persona__grupo", "curso")
        .order_by("pk")
        if cordada_de(i.persona) == nombre
    ]
    for i in equipo:
        if i.curso.evaluacion_id and not i.completada_at:
            sincronizar(i)
    arriba = sum(1 for i in equipo if en_plazo(i))
    meta = Ajustes.actuales().meta_cordada
    return {
        "nombre": nombre,
        "total": len(equipo),
        "arriba": arriba,
        "meta": meta,
        "lograda": len(equipo) > 1 and arriba * 100 >= meta * len(equipo),
        "cuerda": [en_plazo(i) for i in equipo],
        "yo": next(n for n, i in enumerate(equipo) if i.pk == inscripcion.pk),
    }


INSIGNIAS = [
    ("cumbre", "🚩", _("Cumbre"), _("Completa el curso.")),
    ("ventana", "☀️", _("Dentro de la ventana"), _("Complétalo antes de la fecha límite.")),
    (
        "alpino",
        "⚡",
        _("Estilo alpino"),
        _("Ve directo a la evaluación y apruébala al primer intento."),
    ),
    ("cordada", "🪢", _("Cordada completa"), _("Que tu equipo haga cumbre dentro del plazo.")),
    ("guia", "🧭", _("Guía de montaña"), _("Completa todos los cursos de un mismo impacto.")),
]


def _guia(inscripcion):
    """Every published course of one of this course's impacts completed (two or more)."""
    persona = inscripcion.persona
    for impacto in inscripcion.curso.impactos.all():
        cursos = impacto.cursos.exclude(estado=EstadoCurso.BORRADOR)
        if cursos.count() < 2:
            continue
        hechas = Inscripcion.objects.filter(
            persona=persona, curso__in=cursos, completada_at__isnull=False
        ).count()
        if hechas == cursos.count():
            return True
    return False


def insignias(inscripcion, equipo=None):
    """Each badge with whether the person earned it. Computed, never stored: they follow
    what already happened (completion, deadline, the evaluation, the team)."""
    ganadas = {
        "cumbre": bool(inscripcion.completada_at),
        "ventana": en_plazo(inscripcion),
        "cordada": bool(equipo and equipo["lograda"]),
        "guia": bool(inscripcion.completada_at) and _guia(inscripcion),
        "alpino": False,
    }
    if inscripcion.directo_at and inscripcion.curso.evaluacion_id:
        primera = _aprobada(inscripcion)
        ganadas["alpino"] = bool(primera and primera.intento == 1)
    return [
        {"clave": k, "icono": i, "nombre": n, "como": c, "ganada": ganadas[k]}
        for k, i, n, c in INSIGNIAS
    ]
