"""Course design rules: lesson dependencies and what must be fixed before publishing."""

import re
from typing import NamedTuple

from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from apps.formularios.models import EstadoCuestionario

from .models import ALTURAS, JUEGOS, TipoBloque

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


class ItemData(NamedTuple):
    """What a block's validation needs from each of its items."""

    titulo: str = ""
    texto: str = ""
    correcta: bool = False
    grupo: int | None = None


def block_errors(bloque, items=()):
    """What a block still needs for its type. `items`: the ItemData of its steps,
    sections, options or cards."""
    con_titulo = all(i.titulo for i in items)
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
    if bloque.tipo == T.ACORDEON and not con_titulo:
        return [_("cada sección necesita un título")]
    if bloque.tipo in (T.PREGUNTA, T.ESCENARIO):
        if not bloque.texto.strip():
            return [
                _("escribe la pregunta")
                if bloque.tipo == T.PREGUNTA
                else _("describe la situación")
            ]
        if len(items) < 2 or not con_titulo:
            return [_("agrega al menos dos opciones, cada una con su texto")]
        if sum(1 for i in items if i.correcta) != 1:
            return [_("marca una sola opción como correcta")]
    if bloque.tipo == T.ESCENARIO and not all(i.texto.strip() for i in items):
        return [_("escribe qué pasa con cada decisión")]
    if bloque.tipo == T.ORDENAR and (len(items) < 3 or not con_titulo):
        return [_("agrega al menos tres pasos, cada uno con su texto")]
    if bloque.tipo == T.CLASIFICAR:
        grupos = [g for g in bloque.grupos if g]
        if len(grupos) < 2:
            return [_("nombra al menos dos grupos")]
        if len(items) < 3 or not con_titulo:
            return [_("agrega al menos tres tarjetas, cada una con su texto")]
        if not all(i.grupo and i.grupo <= len(grupos) for i in items):
            return [_("elige el grupo de cada tarjeta")]
    if bloque.tipo == T.TARJETAS and (
        len(items) < 2 or not all(i.titulo and i.texto.strip() for i in items)
    ):
        return [_("agrega al menos dos tarjetas, cada una con su frente y su reverso")]
    return []


def _items(bloque):
    return [ItemData(i.titulo, i.texto, i.correcta, i.grupo) for i in bloque.items.all()]


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


def pantallas(bloques):
    """Splits a lesson into screens: at each page break, and around each game, which gets
    a screen of its own. A break's title heads the next screen; when it asks for the game,
    "Continuar" waits until the games of the screen before it are solved."""
    out = [{"titulo": "", "bloques": [], "exigir": False}]

    def nueva(titulo=""):
        if out[-1]["bloques"]:
            out.append({"titulo": titulo, "bloques": [], "exigir": False})
        elif titulo:
            out[-1]["titulo"] = titulo

    for b in bloques:
        if b.tipo == T.CORTE:
            llenas = [p for p in out if p["bloques"]]
            if llenas and b.exigir_juego:
                llenas[-1]["exigir"] = True
            nueva(b.titulo)
            continue
        if b.tipo in JUEGOS:
            nueva()
        out[-1]["bloques"].append(b)
        if b.tipo in JUEGOS:
            nueva()
    out = [p for p in out if p["bloques"]]
    for p in out:
        p["juegos"] = [b.pk for b in p["bloques"] if b.tipo in JUEGOS]
    return out


def para_mostrar(leccion, archivo_url, imagen_url):
    """The lesson's blocks ready for the page: player URL for videos and the URLs the
    files are served at (they differ between the preview and the person's link)."""
    bloques = list(leccion.bloques.prefetch_related("items"))
    for b in bloques:
        b.embed = video_embed(b.url) if b.tipo == T.VIDEO else None
        b.archivo_url = archivo_url(b) if b.archivo else None
        b.lista = list(b.items.all())
        if b.tipo == T.ORDENAR:
            b.pasos, b.json_id = [i.titulo for i in b.lista], f"ordenar-{b.pk}"
        if b.tipo == T.CLASIFICAR:
            b.json_id = f"clasificar-{b.pk}"
            b.tarjetas = {
                "grupos": [g for g in b.grupos if g],
                "tarjetas": [
                    {"titulo": i.titulo, "grupo": i.grupo, "texto": i.texto} for i in b.lista
                ],
            }
        for item in b.lista:
            item.imagen_url = imagen_url(item) if item.imagen else None
    return bloques


# --- The expedition: how a course looks with the mountain theme ---

# One piece of gear per lesson, in order (and around again in long courses).
EQUIPO = [
    ("🥾", gettext_lazy("Botas")),
    ("🧭", gettext_lazy("Brújula")),
    ("⛑️", gettext_lazy("Casco")),
    ("🪢", gettext_lazy("Cuerda")),
    ("⛏️", gettext_lazy("Piolet")),
    ("🧤", gettext_lazy("Guantes")),
    ("🔦", gettext_lazy("Linterna frontal")),
    ("🗺️", gettext_lazy("Mapa")),
]

# The route drawing (viewBox 600 × 300): a peak at (300, 30) over a base from x 40 to 560.
_PIE, _CIMA_Y, _MEDIO, _ALTO = 280, 40, 300, 250


def _punto(t, lado):
    """Where the trail is at height t (0 trailhead, 1 summit), zigzagging side to side."""
    if t >= 1:
        return _MEDIO, _CIMA_Y
    y = _PIE - t * (_PIE - _CIMA_Y)
    media = 260 * (y - 30) / _ALTO
    return round(_MEDIO + lado * 0.55 * media), round(y)


def simular(curso, n):
    """Ids of the first `n` lessons a person could have seen, respecting dependencies.
    Lets the preview show the course partway up."""
    lecciones = list(curso.lecciones.prefetch_related("depende_de"))
    vistas = []
    while len(vistas) < n:
        siguiente = next(
            (
                lec
                for lec in lecciones
                if lec.pk not in vistas and all(d.pk in vistas for d in lec.depende_de.all())
            ),
            None,
        )
        if siguiente is None:
            break
        vistas.append(siguiente.pk)
    return set(vistas)


def expedicion(curso, items, completado=False):
    """Adds camp, altitude and gear to each item of `recorrido` and returns the route:
    lessons are camps on the way up; the evaluation, when there is one, is the summit."""
    base, cumbre = ALTURAS[curso.montana]
    tramos = len(items) + (1 if curso.evaluacion_id else 0) or 1
    vistas = sum(1 for i in items if i["vista"])
    puntos = [{"x": _punto(0, -1)[0], "y": _punto(0, -1)[1], "clase": "inicio"}]
    for k, item in enumerate(items, start=1):
        t = k / tramos
        item["altura"] = round(base + (cumbre - base) * t)
        item["campo"] = _("Cumbre") if t >= 1 else _("Campo %(n)s") % {"n": k}
        item["equipo"] = EQUIPO[(k - 1) % len(EQUIPO)]
        x, y = _punto(t, 1 if k % 2 else -1)
        clase = "vista" if item["vista"] else "bloqueada" if item["faltan"] else "abierta"
        puntos.append({"x": x, "y": y, "clase": clase, "n": k})
    if curso.evaluacion_id:
        puntos.append({"x": _MEDIO, "y": _CIMA_Y, "clase": "vista" if completado else "cima"})
    if completado:
        altura, avance = cumbre, tramos
    else:
        # Summit only by completing: without an evaluation, the last required lesson.
        avance = min(vistas, tramos - 1) if tramos > 1 else 0
        altura = round(base + (cumbre - base) * avance / tramos)
    escalador = puntos[avance] if avance < len(puntos) else puntos[-1]
    return {
        "base": base,
        "cumbre": cumbre,
        "altura": altura,
        "porcentaje": round(100 * avance / tramos),
        "puntos": puntos,
        "ruta": " ".join(f"{p['x']},{p['y']}" for p in puntos),
        "escalador": escalador,
        "completado": completado,
        "mochila": [(item["equipo"], item["vista"]) for item in items],
    }


def ventana(fecha_limite, hoy):
    """The deadline as a weather window: abierta, cerrando (a week or less) or cerrada."""
    if not fecha_limite:
        return None
    dias = (fecha_limite - hoy).days
    estado = "cerrada" if dias < 0 else "cerrando" if dias <= 7 else "abierta"
    return {"estado": estado, "dias": dias, "fecha": fecha_limite}
