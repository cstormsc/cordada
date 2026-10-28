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

from . import cursos
from .forms import CursoForm, LeccionForm
from .models import Curso, EstadoCurso, Leccion

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
        {"cursos": lista.prefetch_related("impactos"), "can_design": A.DESIGN in _actions(request)},
    )


@client_member_required
def crear(request, client_slug):
    _require(request, A.DESIGN)
    form = CursoForm(request.POST or None)
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
    form = CursoForm(request.POST or None, instance=curso)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Cambios guardados."))
        return redirect("aprendizaje:curso", client_slug=client_slug, numero=numero)
    return render(request, "aprendizaje/curso_form.html", {"form": form, "curso": curso})


@client_member_required
def curso(request, client_slug, numero):
    _require(request, A.EDIT, A.DESIGN)
    c = _curso(numero)
    lecciones = list(c.lecciones.prefetch_related("depende_de"))
    return render(
        request,
        "aprendizaje/curso.html",
        {
            "curso": c,
            "lecciones": lecciones,
            "impactos": c.impactos.order_by("numero"),
            "errors": cursos.publish_errors(c) if c.is_draft else [],
            "can_design": A.DESIGN in _actions(request),
            "minutos": sum(leccion.minutos or 0 for leccion in lecciones),
        },
    )


@client_member_required
def leccion(request, client_slug, numero, pk=None):
    _require(request, A.DESIGN)
    c = _curso(numero)
    if pk is None and (resp := _draft_or_redirect(request, c, client_slug)) is not None:
        return resp
    obj = (
        get_object_or_404(Leccion.objects, curso=c, pk=pk)
        if pk
        else Leccion(curso=c, orden=c.lecciones.count() + 1)
    )
    form = LeccionForm(request.POST or None, request.FILES or None, instance=obj, curso=c)
    if request.method == "POST" and form.is_valid():
        obj = form.save()
        messages.success(request, _("Lección guardada."))
        return redirect(f"{_curso_url(client_slug, numero)}#l{obj.pk}")
    return render(
        request, "aprendizaje/leccion_form.html", {"curso": c, "leccion": obj, "form": form}
    )


def _curso_url(client_slug, numero):
    return reverse("aprendizaje:curso", kwargs={"client_slug": client_slug, "numero": numero})


@client_member_required
@require_POST
def borrar_leccion(request, client_slug, numero, pk):
    _require(request, A.DESIGN)
    c = _curso(numero)
    if (resp := _draft_or_redirect(request, c, client_slug)) is not None:
        return resp
    with transaction.atomic():
        get_object_or_404(Leccion.objects, curso=c, pk=pk).delete()
        cursos.renumber(c)
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
    try:
        ids = [int(pk) for pk in json.loads(request.body)["ids"]]
    except (ValueError, KeyError, TypeError):
        return HttpResponseBadRequest()
    with transaction.atomic():
        cursos.renumber(c, ids)
    return HttpResponse(status=204)


@client_member_required
def archivo(request, client_slug, numero, pk):
    _require(request, A.EDIT, A.DESIGN)
    leccion = get_object_or_404(Leccion.objects, curso__numero=numero, pk=pk)
    if not leccion.archivo:
        raise Http404
    ext = os.path.splitext(leccion.archivo.name)[1]
    return FileResponse(
        leccion.archivo.open("rb"), as_attachment=True, filename=f"{leccion.titulo}{ext}"
    )


# --- Preview: the course as the person will see it ---


def _preview_items(request, client_slug, c):
    items = cursos.recorrido(c)
    for item in items:
        item["url"] = reverse(
            "aprendizaje:vista_previa_leccion",
            kwargs={"client_slug": client_slug, "numero": c.numero, "pk": item["leccion"].pk},
        )
    return items


@client_member_required
def vista_previa(request, client_slug, numero):
    _require(request, A.EDIT, A.DESIGN)
    c = _curso(numero)
    items = _preview_items(request, client_slug, c)
    abiertas = [i for i in items if not i["faltan"]]
    return render(
        request,
        "aprendizaje/aprende/portada.html",
        {
            "curso": c,
            "items": items,
            "vistas": 0,
            "continuar": abiertas[0]["url"] if abiertas else None,
            "preview": True,
            "volver": _curso_url(client_slug, numero),
        },
    )


@client_member_required
def vista_previa_leccion(request, client_slug, numero, pk):
    _require(request, A.EDIT, A.DESIGN)
    c = _curso(numero)
    items = _preview_items(request, client_slug, c)
    pos = next((n for n, i in enumerate(items) if i["leccion"].pk == pk), None)
    if pos is None:
        raise Http404
    leccion = items[pos]["leccion"]
    return render(
        request,
        "aprendizaje/aprende/leccion.html",
        {
            "curso": c,
            "item": items[pos],
            "leccion": leccion,
            "numero": pos + 1,
            "total": len(items),
            "anterior": items[pos - 1]["url"] if pos else None,
            "siguiente": items[pos + 1]["url"] if pos + 1 < len(items) else None,
            "portada": reverse(
                "aprendizaje:vista_previa", kwargs={"client_slug": client_slug, "numero": numero}
            ),
            "embed": cursos.video_embed(leccion.url) if leccion.tipo == "video" else None,
            "archivo_url": reverse(
                "aprendizaje:archivo",
                kwargs={"client_slug": client_slug, "numero": numero, "pk": pk},
            )
            if leccion.archivo
            else None,
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
