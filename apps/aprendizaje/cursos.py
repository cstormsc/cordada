"""Course design rules: lesson dependencies and what must be fixed before publishing."""

import re

from django.utils.translation import gettext as _

from apps.formularios.models import EstadoCuestionario

from .models import TipoBloque

T = TipoBloque


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


def block_errors(bloque, items=()):
    """What a block still needs for its type. `items`: (titulo, texto) of its steps or
    sections."""
    if bloque.tipo in (T.TEXTO, T.NOTA) and not bloque.texto.strip():
        return [_("escribe el texto")]
    if bloque.tipo == T.IMAGEN and not bloque.archivo:
        return [_("sube la imagen")]
    if bloque.tipo == T.VIDEO and not bloque.url:
        return [_("pega el enlace del video")]
    if bloque.tipo == T.DOCUMENTO and not (bloque.archivo or bloque.url):
        return [_("sube el documento o pega su enlace")]
    if bloque.tipo == T.PASOS and len(items) < 2:
        return [_("agrega al menos dos pasos")]
    if bloque.tipo == T.ACORDEON and not items:
        return [_("agrega al menos una sección")]
    if bloque.tipo == T.ACORDEON and not all(titulo for titulo, _texto in items):
        return [_("cada sección necesita un título")]
    return []


def _items(bloque):
    return [(i.titulo, i.texto) for i in bloque.items.all()]


def publish_errors(curso):
    """Everything that must be fixed before publishing. Empty list means ready."""
    lecciones = list(curso.lecciones.all())
    if not lecciones:
        return [_("Agrega al menos una lección.")]
    errors = []
    for i, leccion in enumerate(lecciones, start=1):
        bloques = list(leccion.bloques.prefetch_related("items"))
        if not bloques:
            errors.append(_("Lección %(n)s: agrega al menos un bloque.") % {"n": i})
        for j, bloque in enumerate(bloques, start=1):
            for e in block_errors(bloque, _items(bloque)):
                errors.append(_("Lección %(n)s, bloque %(b)s: %(e)s.") % {"n": i, "b": j, "e": e})
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


def renumber(queryset, ids=None):
    """Sets orden 1..n on the rows (lessons, blocks), following `ids` when given."""
    rows = {row.pk: row for row in queryset}
    order = [pk for pk in (ids or []) if pk in rows]
    order += [pk for pk in rows if pk not in order]
    for i, pk in enumerate(order, start=1):
        row = rows[pk]
        if row.orden != i:
            row.orden = i
            row.save(update_fields=["orden"])


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


def para_mostrar(leccion, archivo_url, imagen_url):
    """The lesson's blocks ready for the page: player URL for videos and the URLs the
    files are served at (they differ between the preview and the person's link)."""
    bloques = list(leccion.bloques.prefetch_related("items"))
    for b in bloques:
        b.embed = video_embed(b.url) if b.tipo == T.VIDEO else None
        b.archivo_url = archivo_url(b) if b.archivo else None
        b.lista = list(b.items.all())
        for item in b.lista:
            item.imagen_url = imagen_url(item) if item.imagen else None
    return bloques
