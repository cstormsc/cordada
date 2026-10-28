import csv
import json
import os

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count
from django.http import FileResponse, Http404, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.core.decorators import client_member_required
from apps.core.models import Module
from apps.core.permissions import Action, role_actions
from apps.formularios.forms import EnlacesForm
from apps.formularios.models import Persona
from apps.matriz.export import safe_cell

from . import avance, cursos
from .forms import (
    BLOCK_HELP,
    AjustesForm,
    BloqueForm,
    CursoForm,
    EncabezadoForm,
    LeccionForm,
    item_formset,
    kept_items,
)
from .models import (
    CON_ITEMS,
    Ajustes,
    Bloque,
    BloqueItem,
    Curso,
    Encabezado,
    EstadoCurso,
    Inscripcion,
    Leccion,
    TipoBloque,
)

A = Action


def _actions(request):
    if not request.client.has_module(Module.APRENDIZAJE):
        return frozenset()
    return role_actions(request.membership.role, Module.APRENDIZAJE)


def _require(request, *any_of):
    if not set(any_of) & _actions(request):
        raise PermissionDenied


def _curso(numero):
    return get_object_or_404(Curso.objects.select_related("evaluacion"), numero=numero)


def _draft_or_redirect(request, curso, client_slug):
    if not curso.is_draft:
        messages.error(request, _("El curso ya está publicado: sus lecciones quedan fijas."))
        return redirect("aprendizaje:curso", client_slug=client_slug, numero=curso.numero)
    return None


@client_member_required
def index(request, client_slug):
    _require(request, A.EDIT, A.DESIGN)
    lista = Curso.objects.select_related("evaluacion").annotate(
        n_lecciones=Count("lecciones", distinct=True),
        n_inscritos=Count("inscripciones", distinct=True),
    )
    return render(
        request,
        "aprendizaje/index.html",
        {
            "cursos": lista.prefetch_related("impactos"),
            "can_design": A.DESIGN in _actions(request),
            "can_edit": A.EDIT in _actions(request),
        },
    )


@client_member_required
def crear(request, client_slug):
    _require(request, A.DESIGN)
    form = CursoForm(request.POST or None, expedicion=Ajustes.actuales().expedicion)
    if request.method == "POST" and form.is_valid():
        curso = form.save(commit=False)
        curso.creado_por = request.user
        curso.save()
        form.save_m2m()
        return redirect("aprendizaje:curso", client_slug=client_slug, numero=curso.numero)
    return render(request, "aprendizaje/curso_form.html", {"form": form})


@client_member_required
def editar(request, client_slug, numero):
    _require(request, A.DESIGN)
    curso = _curso(numero)
    form = CursoForm(request.POST or None, instance=curso, expedicion=Ajustes.actuales().expedicion)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Cambios guardados."))
        return redirect("aprendizaje:curso", client_slug=client_slug, numero=numero)
    return render(request, "aprendizaje/curso_form.html", {"form": form, "curso": curso})


@client_member_required
def curso(request, client_slug, numero):
    _require(request, A.EDIT, A.DESIGN)
    c = _curso(numero)
    lecciones = list(c.lecciones.prefetch_related("depende_de", "bloques"))
    for leccion in lecciones:
        bloques = list(leccion.bloques.all())
        leccion.n_bloques = len(bloques)
        leccion.tipos = list(dict.fromkeys(str(b.get_tipo_display()) for b in bloques))
    return render(
        request,
        "aprendizaje/curso.html",
        {
            "curso": c,
            "lecciones": lecciones,
            "impactos": c.impactos.order_by("numero"),
            "errors": cursos.publish_errors(c) if c.is_draft else [],
            "can_design": A.DESIGN in _actions(request),
            "can_edit": A.EDIT in _actions(request),
            "minutos": sum(leccion.minutos or 0 for leccion in lecciones),
        },
    )


def _curso_url(client_slug, numero):
    return reverse("aprendizaje:curso", kwargs={"client_slug": client_slug, "numero": numero})


def _leccion_url(client_slug, numero, pk):
    return reverse(
        "aprendizaje:leccion", kwargs={"client_slug": client_slug, "numero": numero, "pk": pk}
    )


def _json_ids(request):
    try:
        return [int(pk) for pk in json.loads(request.body)["ids"]]
    except (ValueError, KeyError, TypeError):
        return None


@client_member_required
def leccion(request, client_slug, numero, pk=None):
    """New lesson (its settings), or an existing one: its settings and its blocks."""
    _require(request, A.DESIGN)
    c = _curso(numero)
    if pk is None and (resp := _draft_or_redirect(request, c, client_slug)) is not None:
        return resp
    obj = (
        get_object_or_404(Leccion.objects, curso=c, pk=pk)
        if pk
        else Leccion(curso=c, orden=c.lecciones.count() + 1)
    )
    form = LeccionForm(request.POST or None, instance=obj, curso=c)
    if request.method == "POST" and form.is_valid():
        is_new = obj.pk is None
        obj = form.save()
        if is_new:
            messages.success(request, _("Lección creada. Ahora agrégale bloques."))
            return redirect(_leccion_url(client_slug, numero, obj.pk))
        messages.success(request, _("Lección guardada."))
        return redirect(f"{_curso_url(client_slug, numero)}#l{obj.pk}")
    bloques = list(obj.bloques.prefetch_related("items")) if obj.pk else []
    for b in bloques:
        b.errores = cursos.block_errors(b, [(i.titulo, i.texto) for i in b.items.all()])
    return render(
        request,
        "aprendizaje/leccion_form.html",
        {
            "curso": c,
            "leccion": obj,
            "form": form,
            "bloques": bloques,
            "tipos": TipoBloque.choices,
            "tipo_help": BLOCK_HELP,
        },
    )


@client_member_required
@require_POST
def borrar_leccion(request, client_slug, numero, pk):
    _require(request, A.DESIGN)
    c = _curso(numero)
    if (resp := _draft_or_redirect(request, c, client_slug)) is not None:
        return resp
    with transaction.atomic():
        get_object_or_404(Leccion.objects, curso=c, pk=pk).delete()
        cursos.renumber(c.lecciones.all())
    messages.success(request, _("Lección eliminada."))
    return redirect("aprendizaje:curso", client_slug=client_slug, numero=numero)


@client_member_required
@require_POST
def ordenar(request, client_slug, numero):
    """Saves the order the guide dragged the lessons into: {"ids": [leccion_id, ...]}."""
    _require(request, A.DESIGN)
    c = _curso(numero)
    if not c.is_draft:
        return HttpResponseBadRequest(_("El curso ya está publicado."))
    if (ids := _json_ids(request)) is None:
        return HttpResponseBadRequest()
    with transaction.atomic():
        cursos.renumber(c.lecciones.all(), ids)
    return HttpResponse(status=204)


# --- Blocks (content can change after publishing: progress is kept per lesson) ---


def _leccion(numero, pk):
    return get_object_or_404(Leccion.objects.select_related("curso"), curso__numero=numero, pk=pk)


@client_member_required
def bloque(request, client_slug, numero, pk, bloque_pk=None, tipo=None):
    _require(request, A.DESIGN)
    lec = _leccion(numero, pk)
    if bloque_pk:
        obj = get_object_or_404(Bloque.objects, leccion=lec, pk=bloque_pk)
    elif tipo in TipoBloque.values:
        obj = Bloque(leccion=lec, tipo=tipo, orden=lec.bloques.count() + 1)
    else:
        raise Http404
    data, files = (request.POST, request.FILES) if request.method == "POST" else (None, None)
    form = BloqueForm(data, files, instance=obj)
    formset = item_formset(obj, data, files) if obj.tipo in CON_ITEMS else None
    if request.method == "POST" and form.is_valid() and (formset is None or formset.is_valid()):
        kept = kept_items(formset) if formset else []
        probe = form.save(commit=False)
        if errors := cursos.block_errors(probe, [item for _f, item in kept]):
            form.add_error(None, errors[0][:1].upper() + errors[0][1:] + ".")
        else:
            with transaction.atomic():
                obj = form.save()
                if formset:
                    keep = set()
                    for n, (item_form, _item) in enumerate(kept, start=1):
                        item = item_form.save(commit=False)
                        item.bloque, item.orden = obj, n
                        item.save()
                        keep.add(item.pk)
                    obj.items.exclude(pk__in=keep).delete()
            messages.success(request, _("Bloque guardado."))
            return redirect(f"{_leccion_url(client_slug, numero, pk)}#b{obj.pk}")
    return render(
        request,
        "aprendizaje/bloque_form.html",
        {
            "curso": lec.curso,
            "leccion": lec,
            "bloque": obj,
            "form": form,
            "formset": formset,
            "ayuda": BLOCK_HELP.get(obj.tipo),
        },
    )


@client_member_required
@require_POST
def borrar_bloque(request, client_slug, numero, pk, bloque_pk):
    _require(request, A.DESIGN)
    lec = _leccion(numero, pk)
    with transaction.atomic():
        get_object_or_404(Bloque.objects, leccion=lec, pk=bloque_pk).delete()
        cursos.renumber(lec.bloques.all())
    messages.success(request, _("Bloque eliminado."))
    return redirect(_leccion_url(client_slug, numero, pk))


@client_member_required
@require_POST
def ordenar_bloques(request, client_slug, numero, pk):
    _require(request, A.DESIGN)
    lec = _leccion(numero, pk)
    if (ids := _json_ids(request)) is None:
        return HttpResponseBadRequest()
    with transaction.atomic():
        cursos.renumber(lec.bloques.all(), ids)
    return HttpResponse(status=204)


def _serve(f, name, *, inline):
    if not f:
        raise Http404
    ext = os.path.splitext(f.name)[1]
    return FileResponse(f.open("rb"), as_attachment=not inline, filename=f"{name}{ext}")


@client_member_required
def archivo(request, client_slug, numero, bloque_pk):
    _require(request, A.EDIT, A.DESIGN)
    b = get_object_or_404(Bloque.objects, leccion__curso__numero=numero, pk=bloque_pk)
    return _serve(b.archivo, b.titulo or b.leccion.titulo, inline=b.tipo == TipoBloque.IMAGEN)


@client_member_required
def imagen(request, client_slug, numero, item_pk):
    _require(request, A.EDIT, A.DESIGN)
    item = get_object_or_404(BloqueItem.objects, bloque__leccion__curso__numero=numero, pk=item_pk)
    return _serve(item.imagen, item.titulo or "imagen", inline=True)


# --- The client's banner over the course pages ---


@client_member_required
def encabezado(request, client_slug):
    _require(request, A.EDIT)
    actual = Encabezado.objects.first()
    ajustes = AjustesForm(
        request.POST if "ajustes" in request.POST else None, instance=Ajustes.actuales()
    )
    if "ajustes" in request.POST:
        if ajustes.is_valid():
            ajustes.save()
            messages.success(request, _("Ajustes guardados."))
        return redirect("aprendizaje:encabezado", client_slug=client_slug)
    if request.method == "POST" and "quitar" in request.POST:
        if actual:
            actual.delete()
        messages.success(request, _("Encabezado quitado."))
        return redirect("aprendizaje:encabezado", client_slug=client_slug)
    form = EncabezadoForm(
        request.POST or None, request.FILES or None, instance=actual or Encabezado()
    )
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Encabezado guardado."))
        if form.dimensiones and form.dimensiones[0] < Encabezado.ANCHO_MINIMO:
            messages.warning(
                request,
                _(
                    "La imagen mide %(w)s × %(h)s px: en pantallas grandes puede verse "
                    "borrosa. Lo ideal es %(rw)s × %(rh)s px."
                )
                % {
                    "w": form.dimensiones[0],
                    "h": form.dimensiones[1],
                    "rw": Encabezado.ANCHO,
                    "rh": Encabezado.ALTO,
                },
            )
        return redirect("aprendizaje:encabezado", client_slug=client_slug)
    return render(
        request,
        "aprendizaje/encabezado.html",
        {"form": form, "actual": actual, "banner": _banner(client_slug), "ajustes": ajustes},
    )


def _banner(client_slug):
    """{url, alt} of the client's banner, or None. The URL changes with each upload."""
    actual = Encabezado.objects.first()
    if actual is None:
        return None
    url = reverse("aprendizaje:encabezado_imagen", kwargs={"client_slug": client_slug})
    return {"url": f"{url}?v={int(actual.updated_at.timestamp())}", "alt": actual.texto_alternativo}


@client_member_required
def encabezado_imagen(request, client_slug):
    _require(request, A.EDIT, A.DESIGN)
    actual = Encabezado.objects.first()
    return _serve(actual.imagen if actual else None, "encabezado", inline=True)


# --- Preview: the course as the person will see it ---


def _preview_items(client_slug, c, vistas=frozenset()):
    items = cursos.recorrido(c, vistas)
    for item in items:
        item["url"] = reverse(
            "aprendizaje:vista_previa_leccion",
            kwargs={"client_slug": client_slug, "numero": c.numero, "pk": item["leccion"].pk},
        )
    return items


def _preview_vistas(request, c):
    """The progress the preview pretends: ?simular=n sees the first n lessons, and one
    more than the lessons passes the evaluation."""
    try:
        n = max(0, int(request.GET.get("simular", 0)))
    except ValueError:
        n = 0
    total = c.lecciones.count()
    vistas = cursos.simular(c, n)
    completado = n > total if c.evaluacion_id else total > 0 and len(vistas) == total
    return n, vistas, completado


def _expedicion(c, items, completado):
    if not Ajustes.actuales().expedicion:
        return None
    exp = cursos.expedicion(c, items, completado)
    exp["ventana"] = cursos.ventana(c.fecha_limite, timezone.localdate())
    exp["montana"] = c.get_montana_display()
    return exp


def _preview_logros(c, completado):
    """Badges as the simulated progress earns them, and a sample rope team: the preview
    has no real people to count."""
    if not Ajustes.actuales().expedicion:
        return {}
    ganadas = {"cumbre": completado, "ventana": completado and c.fecha_limite is not None}
    arriba = 5 if completado else 3
    return {
        "insignias": [
            {"clave": k, "icono": i, "nombre": n, "como": como, "ganada": ganadas.get(k, False)}
            for k, i, n, como in avance.INSIGNIAS
        ],
        "equipo": {
            "nombre": _("Sucursal Centro"),
            "total": 8,
            "arriba": arriba,
            "meta": Ajustes.actuales().meta_cordada,
            "lograda": False,
            "cuerda": [k < arriba for k in range(8)],
            "yo": 0,
            "ejemplo": True,
        },
    }


@client_member_required
def vista_previa(request, client_slug, numero):
    _require(request, A.EDIT, A.DESIGN)
    c = _curso(numero)
    n, vistas, completado = _preview_vistas(request, c)
    items = _preview_items(client_slug, c, vistas)
    abiertas = [i for i in items if not i["faltan"] and not i["vista"]]
    url = reverse("aprendizaje:vista_previa", kwargs={"client_slug": client_slug, "numero": numero})
    pasos = len(items) + (1 if c.evaluacion_id else 0)
    return render(
        request,
        "aprendizaje/aprende/portada.html",
        {
            "curso": c,
            "items": items,
            "vistas": len(vistas),
            "continuar": abiertas[0]["url"] if abiertas else None,
            "expedicion": _expedicion(c, items, completado),
            **_preview_logros(c, completado),
            "simular": n,
            "simulaciones": [
                {"n": k, "url": f"{url}?simular={k}" if k else url} for k in range(pasos + 1)
            ],
            "banner": _banner(client_slug),
            "preview": True,
            "volver": _curso_url(client_slug, numero),
        },
    )


@client_member_required
def vista_previa_leccion(request, client_slug, numero, pk):
    _require(request, A.EDIT, A.DESIGN)
    c = _curso(numero)
    items = _preview_items(client_slug, c)
    pos = next((n for n, i in enumerate(items) if i["leccion"].pk == pk), None)
    if pos is None:
        raise Http404
    leccion = items[pos]["leccion"]
    expedicion = _expedicion(c, items, False)

    def archivo_url(b):
        return reverse(
            "aprendizaje:archivo",
            kwargs={"client_slug": client_slug, "numero": numero, "bloque_pk": b.pk},
        )

    def imagen_url(item):
        return reverse(
            "aprendizaje:imagen",
            kwargs={"client_slug": client_slug, "numero": numero, "item_pk": item.pk},
        )

    return render(
        request,
        "aprendizaje/aprende/leccion.html",
        {
            "curso": c,
            "item": items[pos],
            "leccion": leccion,
            "bloques": cursos.para_mostrar(leccion, archivo_url, imagen_url),
            "numero": pos + 1,
            "total": len(items),
            "expedicion": expedicion,
            "anterior": items[pos - 1]["url"] if pos else None,
            "siguiente": items[pos + 1]["url"] if pos + 1 < len(items) else None,
            "banner": _banner(client_slug),
            "portada": reverse(
                "aprendizaje:vista_previa", kwargs={"client_slug": client_slug, "numero": numero}
            ),
            "preview": True,
            "volver": _curso_url(client_slug, numero),
        },
    )


@client_member_required
@require_POST
def publicar(request, client_slug, numero):
    _require(request, A.DESIGN)
    c = _curso(numero)
    if (resp := _draft_or_redirect(request, c, client_slug)) is not None:
        return resp
    if errors := cursos.publish_errors(c):
        for e in errors:
            messages.error(request, e)
    else:
        c.estado, c.publicado_at = EstadoCurso.PUBLICADO, timezone.now()
        c.save(update_fields=["estado", "publicado_at"])
        messages.success(
            request,
            _("Publicado. Las lecciones quedan fijas; su contenido todavía se puede corregir."),
        )
    return redirect("aprendizaje:curso", client_slug=client_slug, numero=numero)


@client_member_required
@require_POST
def cerrar(request, client_slug, numero):
    _require(request, A.DESIGN)
    c = _curso(numero)
    if c.estado == EstadoCurso.PUBLICADO:
        c.estado = EstadoCurso.CERRADO
        c.save(update_fields=["estado"])
        messages.success(request, _("Curso cerrado: ya no se puede avanzar en él."))
    return redirect("aprendizaje:curso", client_slug=client_slug, numero=numero)


# --- People: personal links and how far each team got ---


@client_member_required
def inscripciones(request, client_slug, numero):
    _require(request, A.EDIT)
    c = _curso(numero)
    if c.is_draft:
        messages.error(request, _("Publica el curso antes de generar enlaces."))
        return redirect("aprendizaje:curso", client_slug=client_slug, numero=numero)
    form = EnlacesForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        personas = Persona.objects.filter(is_active=True)
        if grupos := form.cleaned_data["grupos"]:
            personas = personas.filter(grupo__in=grupos)
        have = set(c.inscripciones.values_list("persona_id", flat=True))
        nuevas = [p for p in personas if p.pk not in have]
        with transaction.atomic():
            for p in nuevas:
                Inscripcion.objects.create(curso=c, persona=p)
        messages.success(
            request, _("%(n)s enlaces nuevos (cada persona tiene uno solo).") % {"n": len(nuevas)}
        )
        return redirect("aprendizaje:inscripciones", client_slug=client_slug, numero=numero)

    total = c.lecciones.count()
    filas, equipos = [], {}
    lista = c.inscripciones.select_related("persona__grupo", "curso").annotate(
        n_vistas=Count("vistas")
    )
    for ins in lista.order_by("persona__apellido", "persona__nombre", "persona__email"):
        avance.sincronizar(ins)
        nombre = avance.cordada_de(ins.persona) or _("Sin equipo")
        en_plazo = avance.en_plazo(ins)
        e = equipos.setdefault(
            nombre, {"nombre": nombre, "total": 0, "iniciaron": 0, "arriba": 0, "plazo": 0}
        )
        e["total"] += 1
        e["iniciaron"] += bool(ins.iniciada_at)
        e["arriba"] += bool(ins.completada_at)
        e["plazo"] += en_plazo
        filas.append({"ins": ins, "cordada": nombre, "en_plazo": en_plazo})
    meta = Ajustes.actuales().meta_cordada
    for e in equipos.values():
        e["porcentaje"] = round(100 * e["plazo"] / e["total"])
        e["lograda"] = e["total"] > 1 and e["plazo"] * 100 >= meta * e["total"]
    return render(
        request,
        "aprendizaje/inscripciones.html",
        {
            "curso": c,
            "form": form,
            "total_lecciones": total,
            "filas": filas if A.VIEW_INDIVIDUAL in _actions(request) else None,
            "n_inscritos": len(filas),
            "equipos": sorted(equipos.values(), key=lambda e: (-e["porcentaje"], e["nombre"])),
            "meta": meta,
            "enlace_dias": Inscripcion.validez().days,
        },
    )


@client_member_required
def exportar_inscripciones(request, client_slug, numero):
    """Exports the personal links so the client sends them from its own email, like
    Formularios does."""
    _require(request, A.EDIT)
    c = _curso(numero)
    vence = timezone.localdate() + Inscripcion.validez()  # signed now, by i.token
    rows = [
        [
            i.persona.email,
            i.persona.nombre,
            i.persona.apellido,
            str(i.persona.grupo or ""),
            avance.cordada_de(i.persona) or "",
            request.build_absolute_uri(reverse("aprende:portada", kwargs={"token": i.token})),
            vence.isoformat(),
        ]
        for i in c.inscripciones.select_related("persona__grupo").order_by("persona__email")
    ]
    headers = ["correo", "nombre", "apellido", "grupo", "cordada", "enlace", "vence"]
    filename = f"enlaces-{c.codigo.lower()}-{request.client.slug}"
    if request.GET.get("formato") == "csv":
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{filename}.csv"'
        response.write("\ufeff")  # Excel opens UTF-8 CSV correctly with a BOM
        writer = csv.writer(response)
        writer.writerow(headers)
        writer.writerows([[safe_cell(v) for v in row] for row in rows])
        return response
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    ws = wb.active
    ws.title = "Enlaces"
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for row in rows:
        ws.append([safe_cell(v) for v in row])
    ws.column_dimensions["F"].width = 80
    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}.xlsx"'
    wb.save(response)
    return response
