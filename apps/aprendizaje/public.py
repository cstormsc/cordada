"""Taking a course through a personal link. No account: the signed token identifies the
person, like Formularios' links."""

import os

from django.db import transaction
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.clickjacking import xframe_options_deny
from django.views.decorators.http import require_POST

from apps.core.models import Module
from apps.core.tenancy import tenant_context
from apps.formularios.models import Enlace

from . import avance, cursos
from .models import Ajustes, Bloque, BloqueItem, Encabezado, EstadoCurso, Inscripcion, LeccionVista


def _url(name, token, **kwargs):
    return reverse(f"aprende:{name}", kwargs={"token": token, **kwargs})


def _cerrado(request, inscripcion, message):
    return render(
        request,
        "aprendizaje/aprende/cerrado.html",
        {"curso": inscripcion.curso, "message": message},
        status=410,
    )


def con_inscripcion(view):
    """Resolves the token and runs the view inside the client's tenant, or answers 404
    (unknown link) or 410 (expired link, closed course)."""

    @never_cache
    @xframe_options_deny
    def wrapper(request, token, **kwargs):
        ins = Inscripcion.from_token(token)
        if (
            ins is None
            or not ins.client.is_active
            or not ins.client.has_module(Module.APRENDIZAJE)
            or not ins.persona.is_active
            or ins.curso.estado == EstadoCurso.BORRADOR
        ):
            raise Http404
        with tenant_context(ins.client):
            if ins.vencido:
                return _cerrado(
                    request, ins, _("Este enlace venció. Pide uno nuevo a quien te lo envió.")
                )
            if ins.curso.estado == EstadoCurso.CERRADO:
                return _cerrado(request, ins, _("Este curso ya cerró."))
            return view(request, token, ins, **kwargs)

    return wrapper


def _banner(token):
    actual = Encabezado.objects.first()
    if actual is None:
        return None
    url = _url("encabezado", token)
    return {"url": f"{url}?v={int(actual.updated_at.timestamp())}", "alt": actual.texto_alternativo}


def _estado(token, ins):
    """The course as this person has climbed it so far."""
    vistas = set(ins.vistas.values_list("leccion_id", flat=True))
    avance.sincronizar(ins, vistas)
    items = cursos.recorrido(ins.curso, vistas)
    for item in items:
        item["url"] = _url("leccion", token, pk=item["leccion"].pk)
    expedicion = None
    if Ajustes.actuales().expedicion:
        expedicion = cursos.expedicion(ins.curso, items, bool(ins.completada_at))
        expedicion["ventana"] = cursos.ventana(ins.curso.fecha_limite, timezone.localdate())
        expedicion["montana"] = ins.curso.get_montana_display()
    obligatorias = [i for i in items if i["leccion"].obligatoria]
    return {
        "vistas": vistas,
        "items": items,
        "expedicion": expedicion,
        "puede_evaluar": bool(ins.curso.evaluacion_id)
        and (bool(ins.directo_at) or all(i["vista"] for i in obligatorias)),
    }


def _comun(token, ins):
    return {
        "curso": ins.curso,
        "inscripcion": ins,
        "persona": ins.persona.nombre or ins.persona.email,
        "banner": _banner(token),
        "portada": _url("portada", token),
    }


@con_inscripcion
def portada(request, token, ins):
    estado = _estado(token, ins)
    items = estado["items"]
    siguiente = next((i for i in items if not i["vista"] and not i["faltan"]), None)
    equipo = medallas = None
    if estado["expedicion"]:
        equipo = avance.cordada(ins)
        medallas = avance.insignias(ins, equipo)
    return render(
        request,
        "aprendizaje/aprende/portada.html",
        {
            **_comun(token, ins),
            **estado,
            "vistas": len(estado["vistas"]),
            "continuar": siguiente["url"] if siguiente else None,
            "equipo": equipo,
            "insignias": medallas,
            "directo_url": _url("directo", token),
            "evaluacion_url": _url("evaluacion", token),
            "bloqueada": request.GET.get("bloqueada"),
        },
    )


@con_inscripcion
def leccion(request, token, ins, pk):
    estado = _estado(token, ins)
    items = estado["items"]
    pos = next((n for n, i in enumerate(items) if i["leccion"].pk == pk), None)
    if pos is None:
        raise Http404
    if items[pos]["faltan"]:
        return redirect(f"{_url('portada', token)}?bloqueada={pk}")
    if not ins.iniciada_at:
        ins.iniciada_at = timezone.now()
        ins.save(update_fields=["iniciada_at"])
    lec = items[pos]["leccion"]
    return render(
        request,
        "aprendizaje/aprende/leccion.html",
        {
            **_comun(token, ins),
            "item": items[pos],
            "leccion": lec,
            "bloques": cursos.para_mostrar(
                lec,
                lambda b: _url("archivo", token, bloque_pk=b.pk),
                lambda item: _url("imagen", token, item_pk=item.pk),
            ),
            "numero": pos + 1,
            "total": len(items),
            "anterior": items[pos - 1]["url"] if pos else None,
            "siguiente": items[pos + 1]["url"] if pos + 1 < len(items) else None,
            "expedicion": estado["expedicion"],
            "marcar_url": _url("marcar", token, pk=pk),
        },
    )


@require_POST
@con_inscripcion
def marcar(request, token, ins, pk):
    lec = get_object_or_404(ins.curso.lecciones, pk=pk)
    items = cursos.recorrido(ins.curso, set(ins.vistas.values_list("leccion_id", flat=True)))
    if any(i["leccion"].pk == pk and i["faltan"] for i in items):
        return redirect(f"{_url('portada', token)}?bloqueada={pk}")
    with transaction.atomic():
        LeccionVista.objects.get_or_create(inscripcion=ins, leccion=lec)
        if not ins.iniciada_at:
            ins.iniciada_at = timezone.now()
            ins.save(update_fields=["iniciada_at"])
    estado = _estado(token, ins)  # also completes a course without evaluation
    siguiente = next((i for i in estado["items"] if not i["vista"] and not i["faltan"]), None)
    return redirect(siguiente["url"] if siguiente else _url("portada", token))


@require_POST
@con_inscripcion
def directo(request, token, ins):
    if not ins.curso.evaluacion_id or not request.POST.get("confirmo"):
        return redirect(_url("portada", token))
    if not ins.directo_at:
        ins.directo_at = timezone.now()
        ins.iniciada_at = ins.iniciada_at or ins.directo_at
        ins.save(update_fields=["directo_at", "iniciada_at"])
    return redirect(_url("evaluacion", token))


@con_inscripcion
def evaluacion(request, token, ins):
    if not _estado(token, ins)["puede_evaluar"]:
        return redirect(_url("portada", token))
    enlace, _created = Enlace.objects.get_or_create(
        cuestionario=ins.curso.evaluacion, persona=ins.persona
    )
    return redirect("formularios_responder", token=enlace.token)


def _serve(f, name, *, inline):
    if not f:
        raise Http404
    ext = os.path.splitext(f.name)[1]
    return FileResponse(f.open("rb"), as_attachment=not inline, filename=f"{name}{ext}")


@con_inscripcion
def archivo(request, token, ins, bloque_pk):
    b = get_object_or_404(Bloque.objects, leccion__curso=ins.curso, pk=bloque_pk)
    return _serve(b.archivo, b.titulo or b.leccion.titulo, inline=b.tipo == "imagen")


@con_inscripcion
def imagen(request, token, ins, item_pk):
    item = get_object_or_404(BloqueItem.objects, bloque__leccion__curso=ins.curso, pk=item_pk)
    return _serve(item.imagen, item.titulo or "imagen", inline=True)


@con_inscripcion
def encabezado(request, token, ins):
    actual = Encabezado.objects.first()
    return _serve(actual.imagen if actual else None, "encabezado", inline=True)
