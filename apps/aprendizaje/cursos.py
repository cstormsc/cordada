"""Course design rules: lesson dependencies and what must be fixed before publishing."""

import re

from django.utils.translation import gettext as _

from apps.formularios.models import EstadoCuestionario

from .models import TipoLeccion


def dependency_graph(curso):
    """{leccion_id: {ids it depends on}} for every lesson of the course."""
    graph = {pk: set() for pk in curso.lecciones.values_list("pk", flat=True)}
    through = curso.lecciones.model.depende_de.through
    for desde, hacia in through.objects.filter(from_leccion__curso=curso).values_list(
        "from_leccion_id", "to_leccion_id"
    ):
        graph.setdefault(desde, set()).add(hacia)
    return graph


def creates_cycle(graph, leccion_id, depende_de_ids):
    """True if `leccion_id` depending on `depende_de_ids` would close a loop."""
    graph = {**graph, leccion_id: set(depende_de_ids)}
    seen, frontier = set(), set(depende_de_ids)
    while frontier:
        if leccion_id in frontier:
            return True
        seen |= frontier
        frontier = {d for pk in frontier for d in graph.get(pk, ())} - seen
    return False


def lesson_errors(leccion):
    """Content a lesson needs for its type."""
    if leccion.tipo == TipoLeccion.TEXTO and not leccion.contenido.strip():
        return [_("escribe el contenido")]
    if leccion.tipo == TipoLeccion.VIDEO and not leccion.url:
        return [_("pega el enlace del video")]
    if leccion.tipo == TipoLeccion.DOCUMENTO and not (leccion.archivo or leccion.url):
        return [_("sube el documento o pega su enlace")]
    return []


def publish_errors(curso):
    """Everything that must be fixed before publishing. Empty list means ready."""
    lecciones = list(curso.lecciones.all())
    if not lecciones:
        return [_("Agrega al menos una lección.")]
    errors = []
    for i, leccion in enumerate(lecciones, start=1):
        for e in lesson_errors(leccion):
            errors.append(_("Lección %(n)s: %(e)s.") % {"n": i, "e": e})
    if curso.evaluacion_id and curso.evaluacion.estado != EstadoCuestionario.PUBLICADO:
        errors.append(
            _("La evaluación %(c)s debe estar publicada en Formularios.")
            % {"c": curso.evaluacion.codigo}
        )
    if not curso.evaluacion_id and not any(leccion.obligatoria for leccion in lecciones):
        errors.append(
            _(
                "Sin evaluación, marca al menos una lección obligatoria para poder "
                "completar el curso."
            )
        )
    return errors


def renumber(curso, ids=None):
    """Sets orden 1..n, following `ids` (lesson ids in the new order) when given."""
    lecciones = {leccion.pk: leccion for leccion in curso.lecciones.all()}
    order = [pk for pk in (ids or []) if pk in lecciones]
    order += [pk for pk in lecciones if pk not in order]
    for i, pk in enumerate(order, start=1):
        leccion = lecciones[pk]
        if leccion.orden != i:
            leccion.orden = i
            leccion.save(update_fields=["orden"])


def recorrido(curso, vistas=frozenset()):
    """The course as a person sees it: each lesson with whether it was seen and, if
    locked, the lessons still missing. `vistas` holds the ids of the lessons seen."""
    lecciones = list(curso.lecciones.prefetch_related("depende_de"))
    items = []
    for leccion in lecciones:
        faltan = [d for d in leccion.depende_de.all() if d.pk not in vistas]
        items.append({"leccion": leccion, "vista": leccion.pk in vistas, "faltan": faltan})
    return items


_YOUTUBE = re.compile(
    r"^https?://(?:www\.|m\.)?(?:youtube\.com/(?:watch\?(?:.*&)?v=|embed/|shorts/|live/)"
    r"|youtu\.be/)([\w-]{11})"
)
_VIMEO = re.compile(r"^https?://(?:www\.)?vimeo\.com/(\d+)(?:/(\w+))?")


def video_embed(url):
    """Player URL for YouTube and Vimeo links, or None (shown as a plain link)."""
    if m := _YOUTUBE.match(url or ""):
        return f"https://www.youtube-nocookie.com/embed/{m[1]}"
    if m := _VIMEO.match(url or ""):
        return f"https://player.vimeo.com/video/{m[1]}" + (f"?h={m[2]}" if m[2] else "")
    return None
