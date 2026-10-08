from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.catalogs.models import GrupoImpactado
from apps.core.decorators import client_member_required
from apps.core.models import Module
from apps.core.permissions import Action, can

from . import export, workflow
from .forms import (
    AdjuntoForm,
    ComentarioForm,
    FiltroForm,
    FotoForm,
    ImpactoForm,
    PriorityOverrideForm,
    ProposalForm,
)
from .models import Adjunto, Estado, Foto, Impacto, sin_criterio_q


def _can(request, action):
    return can(request.user, request.client, Module.MATRIZ, action,
               membership=request.membership)


def _require(request, action):
    if not _can(request, action):
        raise PermissionDenied


def _get_impacto(request, numero):
    """Viewers see every impact; proposers only their own."""
    impacto = get_object_or_404(Impacto.objects.select_related(
        "grupo", "tipo", "tiempo", "origen", "responsable", "registrado_por"), numero=numero)
    if _can(request, Action.VIEW):
        return impacto
    if _can(request, Action.PROPOSE) and impacto.registrado_por_id == request.user.pk:
        return impacto
    raise Http404


def _can_edit_proposal(request, impacto):
    return (impacto.registrado_por_id == request.user.pk
            and impacto.estado == Estado.PROPUESTO and _can(request, Action.PROPOSE))


@client_member_required
def index(request, client_slug):
    if not _can(request, Action.VIEW):
        if _can(request, Action.PROPOSE):
            return redirect("matriz:mis_propuestas", client_slug=client_slug)
        raise PermissionDenied
    filtro = FiltroForm(request.GET or None)
    impactos = filtro.filter(Impacto.objects.select_related("grupo", "tipo", "tiempo",
                                                            "responsable"))
    all_impactos = Impacto.objects.all()
    return render(request, "matriz/index.html", {
        "filtro": filtro,
        "impactos": impactos,
        "can_edit": _can(request, Action.EDIT),
        "querystring": request.GET.urlencode(),
        "resumen": {
            "total": all_impactos.count(),
            "propuestos": all_impactos.filter(estado=Estado.PROPUESTO).count(),
            "p1_sin_criterio": all_impactos.filter(sin_criterio_q(), prioridad=1).count(),
            "extrema": all_impactos.filter(severidad=4).exclude(
                estado__in=[Estado.CERRADO, Estado.DESCARTADO]).count(),
        },
    })


@client_member_required
def mis_propuestas(request, client_slug):
    _require(request, Action.PROPOSE)
    impactos = Impacto.objects.filter(registrado_por=request.user).select_related("grupo")
    return render(request, "matriz/mis_propuestas.html", {"impactos": impactos})


@client_member_required
def crear(request, client_slug):
    if _can(request, Action.EDIT):
        form_class = ImpactoForm
    elif _can(request, Action.PROPOSE):
        form_class = ProposalForm
    else:
        raise PermissionDenied
    form = form_class(request.POST or None, client=request.client)
    if request.method == "POST" and form.is_valid():
        impacto = form.save(commit=False)
        impacto.registrado_por = request.user
        impacto.save()
        messages.success(request, _("%(codigo)s registrado como Propuesto.")
                         % {"codigo": impacto.codigo})
        return redirect("matriz:detalle", client_slug=client_slug, numero=impacto.numero)
    return render(request, "matriz/form.html", {
        "form": form, "can_create_group": _can(request, Action.EDIT),
    })


@client_member_required
def editar(request, client_slug, numero):
    impacto = _get_impacto(request, numero)
    if _can(request, Action.EDIT):
        form_class = ImpactoForm
    elif _can_edit_proposal(request, impacto):
        form_class = ProposalForm
    else:
        raise PermissionDenied
    if impacto.is_locked:
        messages.error(request, _("Reabre el impacto para editarlo."))
        return redirect("matriz:detalle", client_slug=client_slug, numero=numero)
    form = form_class(request.POST or None, instance=impacto, client=request.client)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Cambios guardados."))
        return redirect("matriz:detalle", client_slug=client_slug, numero=numero)
    return render(request, "matriz/form.html", {
        "form": form, "impacto": impacto, "can_create_group": _can(request, Action.EDIT),
    })


@client_member_required
def detalle(request, client_slug, numero):
    impacto = _get_impacto(request, numero)
    can_edit = _can(request, Action.EDIT)
    return render(request, "matriz/detalle.html", {
        "impacto": impacto,
        "can_edit": can_edit,
        "can_edit_proposal": _can_edit_proposal(request, impacto),
        "transitions": workflow.available(impacto) if can_edit else [],
        "missing": workflow.missing_fields(impacto),
        "priority_form": PriorityOverrideForm(instance=impacto),
        "comentario_form": ComentarioForm(),
        "adjunto_form": AdjuntoForm(),
        "grupos": GrupoImpactado.objects.filter(is_active=True),
        "historial": _historial(impacto),
        "transiciones": impacto.transiciones.select_related("usuario"),
    })


def _historial(impacto):
    """[(record, [changed field labels])], newest first, skipping no-op saves."""
    records = list(impacto.history.select_related("history_user").order_by("-history_date"))
    rows = []
    for newer, older in zip(records, [*records[1:], None], strict=True):
        if older is None:
            rows.append((newer, [_("creado")]))
            continue
        delta = newer.diff_against(older)
        labels = [Impacto._meta.get_field(c.field).verbose_name for c in delta.changes]
        if labels:
            rows.append((newer, labels))
    return rows


@client_member_required
@require_POST
def cambiar_estado(request, client_slug, numero):
    _require(request, Action.EDIT)
    impacto = _get_impacto(request, numero)
    try:
        workflow.transition(impacto, request.POST.get("hacia"), user=request.user,
                            reason=request.POST.get("motivo", ""))
        messages.success(request,
                         _("Estado: %(estado)s.") % {"estado": impacto.get_estado_display()})
    except workflow.TransitionError as e:
        for m in e.messages:
            messages.error(request, m)
    return redirect("matriz:detalle", client_slug=client_slug, numero=numero)


@client_member_required
@require_POST
def ajustar_prioridad(request, client_slug, numero):
    _require(request, Action.EDIT)
    impacto = _get_impacto(request, numero)
    form = PriorityOverrideForm(request.POST, instance=impacto)
    if form.is_valid():
        form.save()
        messages.success(request, _("Prioridad actualizada."))
    else:
        for errors in form.errors.values():
            for e in errors:
                messages.error(request, e)
    return redirect("matriz:detalle", client_slug=client_slug, numero=numero)


@client_member_required
@require_POST
def comentar(request, client_slug, numero):
    impacto = _get_impacto(request, numero)
    form = ComentarioForm(request.POST)
    if form.is_valid():
        comentario = form.save(commit=False)
        comentario.impacto, comentario.autor = impacto, request.user
        comentario.save()
    return redirect(f"{impacto_url(client_slug, numero)}#comentarios")


@client_member_required
@require_POST
def adjuntar(request, client_slug, numero):
    impacto = _get_impacto(request, numero)
    if not (_can(request, Action.EDIT) or _can_edit_proposal(request, impacto)):
        raise PermissionDenied
    form = AdjuntoForm(request.POST, request.FILES)
    if form.is_valid():
        adjunto = form.save(commit=False)
        adjunto.impacto, adjunto.subido_por = impacto, request.user
        adjunto.nombre = form.cleaned_data["nombre"]
        adjunto.save()
        messages.success(request, _("Adjunto agregado."))
    else:
        for errors in form.errors.values():
            for e in errors:
                messages.error(request, e)
    return redirect(f"{impacto_url(client_slug, numero)}#adjuntos")


@client_member_required
def descargar_adjunto(request, client_slug, numero, pk):
    impacto = _get_impacto(request, numero)
    adjunto = get_object_or_404(Adjunto.objects, impacto=impacto, pk=pk)
    if not adjunto.archivo:
        raise Http404  # links are shown directly on the page
    return FileResponse(adjunto.archivo.open("rb"), as_attachment=True,
                        filename=adjunto.nombre or adjunto.archivo.name)


@client_member_required
@require_POST
def resolver_grupo_sugerido(request, client_slug, numero):
    """Turns a proposer's suggested group into a real one, or maps it to an existing one."""
    _require(request, Action.EDIT)
    impacto = _get_impacto(request, numero)
    if request.POST.get("grupo"):
        grupo = get_object_or_404(GrupoImpactado.objects, pk=request.POST["grupo"])
    else:
        grupo, _created = _get_or_create_grupo(impacto.grupo_sugerido)
    impacto.grupo, impacto.grupo_sugerido = grupo, ""
    impacto.save()
    messages.success(request, _("Grupo asignado: %(grupo)s.") % {"grupo": grupo.name})
    return redirect("matriz:detalle", client_slug=client_slug, numero=numero)


def _get_or_create_grupo(name):
    name = " ".join(name.split())
    existing = GrupoImpactado.objects.filter(name__iexact=name).first()
    if existing:
        return existing, False
    try:
        with transaction.atomic():
            return GrupoImpactado.objects.create(name=name), True
    except IntegrityError:  # created concurrently
        return GrupoImpactado.objects.get(name__iexact=name), False


@client_member_required
@require_POST
def crear_grupo(request, client_slug):
    """htmx: creates a group from the impact form and returns the refreshed selector."""
    _require(request, Action.EDIT)
    name = " ".join(request.POST.get("nuevo_grupo", "").split())
    context = {"can_create_group": True}
    if not name:
        context["grupo_error"] = _("Escribe el nombre del grupo.")
        selected = request.POST.get("grupo")
    else:
        grupo, created = _get_or_create_grupo(name)
        if not grupo.is_active:
            grupo.is_active = True
            grupo.save(update_fields=["is_active"])
        selected = grupo.pk
        context["grupo_message"] = (
            _("Grupo «%(name)s» creado y seleccionado.") if created
            else _("Ya existía «%(name)s»; quedó seleccionado.")
        ) % {"name": grupo.name}
    form = ImpactoForm(initial={"grupo": selected}, client=request.client)
    context["field"] = form["grupo"]
    return render(request, "matriz/_grupo_field.html", context)


@client_member_required
def exportar(request, client_slug):
    _require(request, Action.VIEW)
    filtro = FiltroForm(request.GET or None)
    impactos = filtro.filter(Impacto.objects.select_related(
        "grupo", "tipo", "tiempo", "origen", "responsable", "responsable_categoria",
        "criterio_evidencia", "tipo_cambio_conocimiento", "formacion_momento"))
    rows = export.impacto_rows(impactos)
    return _xlsx_response(export.workbook(rows, request.client.name),
                          f"matriz-{request.client.slug}.xlsx")


def _xlsx_response(workbook, filename):
    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    workbook.save(response)
    return response


@client_member_required
def fotos(request, client_slug):
    _require(request, Action.VIEW)
    can_edit = _can(request, Action.EDIT)
    form = FotoForm(request.POST or None)
    if request.method == "POST":
        _require(request, Action.EDIT)
        if form.is_valid():
            foto = form.save(commit=False)
            foto.creada_por = request.user
            foto.datos = export.impacto_rows(Impacto.objects.select_related(
                "grupo", "tipo", "tiempo", "origen", "responsable", "responsable_categoria",
                "criterio_evidencia", "tipo_cambio_conocimiento", "formacion_momento"))
            foto.save()
            messages.success(request, _("Foto de la matriz guardada (%(n)s impactos).")
                             % {"n": len(foto.datos)})
            return redirect("matriz:fotos", client_slug=client_slug)
    return render(request, "matriz/fotos.html", {
        "fotos": Foto.objects.select_related("tiempo", "creada_por"),
        "form": form, "can_edit": can_edit,
    })


@client_member_required
def exportar_foto(request, client_slug, pk):
    _require(request, Action.VIEW)
    foto = get_object_or_404(Foto.objects.select_related("tiempo"), pk=pk)
    title = f"{request.client.name} · {foto.tiempo} · {foto.fecha:%Y-%m-%d}"
    return _xlsx_response(export.workbook(foto.datos, title),
                          f"matriz-{request.client.slug}-{foto.fecha:%Y%m%d}.xlsx")


def impacto_url(client_slug, numero):
    from django.urls import reverse

    return reverse("matriz:detalle", kwargs={"client_slug": client_slug, "numero": numero})
