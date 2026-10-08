from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST
from openpyxl import Workbook
from openpyxl.styles import Font

from apps.core.attachments import file_response
from apps.core.decorators import client_member_required
from apps.core.models import Module
from apps.core.permissions import Action, can
from apps.matriz.export import safe_cell
from apps.matriz.models import Impacto

from . import reports
from .forms import ActividadForm, EvidenciaForm, FiltroForm, InformeForm
from .models import Actividad, Evidencia


def _can(request, action, module=Module.RUTA):
    return can(request.user, request.client, module, action, membership=request.membership)


def _require(request, action):
    if not _can(request, action):
        raise PermissionDenied


def _visible(request):
    """Every activity for viewers; captains only those of their groups."""
    if _can(request, Action.VIEW):
        return Actividad.objects.all()
    if _can(request, Action.VIEW_OWN_GROUP):
        return Actividad.objects.of_groups(request.membership.grupos.all())
    raise PermissionDenied


def _get(request, numero):
    return get_object_or_404(_visible(request).select_related(
        "frente", "tiempo", "responsable", "canal", "registrado_por"), numero=numero)


@client_member_required
def index(request, client_slug):
    actividades = _visible(request)
    own_group_only = not _can(request, Action.VIEW)
    grupos = request.membership.grupos.all() if own_group_only else None
    filtro = FiltroForm(request.GET or None, grupos=grupos)
    listed = filtro.filter(actividades.with_cumplimiento()).select_related(
        "frente", "tiempo", "responsable").prefetch_related("grupos", "impactos")
    return render(request, "ruta/index.html", {
        "filtro": filtro,
        "actividades": listed,
        "can_edit": _can(request, Action.EDIT),
        "can_report": _can(request, Action.VIEW),
        "own_group_only": own_group_only,
        "querystring": request.GET.urlencode(),
        "resumen": None if own_group_only else {
            "total": actividades.count(),
            "huerfanas": actividades.huerfanas().count(),
            "descubiertos": reports.descubiertos().count(),
            "no_realizadas": actividades.with_cumplimiento().filter(
                cumplimiento="no_realizada").count(),
        },
    })


def _form_response(request, form, actividad=None):
    return render(request, "ruta/form.html", {"form": form, "actividad": actividad})


@client_member_required
def crear(request, client_slug):
    _require(request, Action.EDIT)
    initial = {}
    if numero := request.GET.get("impacto"):
        impacto = Impacto.objects.filter(numero=numero).select_related("grupo", "tiempo").first()
        if impacto:
            initial = {"impactos": [impacto.pk], "tiempo": impacto.tiempo_id,
                       "grupos": [impacto.grupo_id] if impacto.grupo_id else []}
    form = ActividadForm(request.POST or None, initial=initial, client=request.client)
    if request.method == "POST" and form.is_valid():
        actividad = form.save(commit=False)
        actividad.registrado_por = request.user
        actividad.save()
        form.save_m2m()
        messages.success(request, _("%(codigo)s creada.") % {"codigo": actividad.codigo})
        return redirect("ruta:detalle", client_slug=client_slug, numero=actividad.numero)
    return _form_response(request, form)


@client_member_required
def editar(request, client_slug, numero):
    _require(request, Action.EDIT)
    actividad = _get(request, numero)
    form = ActividadForm(request.POST or None, instance=actividad, client=request.client)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Cambios guardados."))
        return redirect("ruta:detalle", client_slug=client_slug, numero=numero)
    return _form_response(request, form, actividad)


@client_member_required
def detalle(request, client_slug, numero):
    actividad = _get(request, numero)
    can_view_matrix = _can(request, Action.VIEW, Module.MATRIZ)
    return render(request, "ruta/detalle.html", {
        "actividad": actividad,
        "cumplimiento": actividad.get_cumplimiento(),
        "can_edit": _can(request, Action.EDIT),
        "can_view_matrix": can_view_matrix,
        "impactos": actividad.impactos.all() if can_view_matrix else None,
        "adjunto_form": EvidenciaForm(),
    })


@client_member_required
@require_POST
def adjuntar(request, client_slug, numero):
    _require(request, Action.EDIT)
    actividad = _get(request, numero)
    form = EvidenciaForm(request.POST, request.FILES)
    if form.is_valid():
        form.save_for(request.user, actividad=actividad)
        messages.success(request, _("Evidencia agregada."))
    else:
        for errors in form.errors.values():
            for e in errors:
                messages.error(request, e)
    return redirect("ruta:detalle", client_slug=client_slug, numero=numero)


@client_member_required
def descargar(request, client_slug, numero, pk):
    actividad = _get(request, numero)
    return file_response(get_object_or_404(Evidencia.objects, actividad=actividad, pk=pk))


def _informe_context(request):
    form = InformeForm(request.GET or None)
    params = form.cleaned_data if form.is_valid() else {}
    return {
        "form": form,
        "params": params,
        "informe": reports.informe(Actividad.objects.all(), **{
            k: params.get(k) for k in ("tiempo", "mes", "frente")}),
        "generated": timezone.localtime(),
        "querystring": request.GET.urlencode(),
    }


@client_member_required
def informe(request, client_slug):
    _require(request, Action.VIEW)
    return render(request, "ruta/informe.html", _informe_context(request))


@client_member_required
def informe_pdf(request, client_slug):
    _require(request, Action.VIEW)
    from weasyprint import HTML

    html = render_to_string("ruta/informe_pdf.html", _informe_context(request), request=request)
    pdf = HTML(string=html, base_url=request.build_absolute_uri("/")).write_pdf()
    response = HttpResponse(pdf, content_type="application/pdf")
    stamp = timezone.localdate().isoformat()
    response["Content-Disposition"] = (
        f'attachment; filename="cumplimiento-{request.client.slug}-{stamp}.pdf"')
    return response


@client_member_required
def exportar(request, client_slug):
    _require(request, Action.VIEW)
    filtro = FiltroForm(request.GET or None)
    actividades = filtro.filter(Actividad.objects.with_cumplimiento()).select_related(
        "frente", "tiempo", "responsable", "canal").prefetch_related("grupos", "impactos")
    wb = Workbook()
    ws = wb.active
    ws.title = "Ruta"
    headers = ["ID", "Actividad", "Frente", "Tiempo", "Impactos", "Grupos", "Responsable",
               "Fecha planificada", "Fecha real", "Estado", "Cumplimiento", "Canal", "Vocero",
               "Evidencia", "Indicador", "No planificada"]
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    labels = dict(reports.C.choices)
    for a in actividades:
        ws.append([safe_cell(v) for v in [
            a.codigo, a.titulo, str(a.frente), str(a.tiempo or ""),
            ", ".join(i.codigo for i in a.impactos.all()),
            ", ".join(g.name for g in a.grupos.all()),
            a.responsable.display_name if a.responsable else "",
            a.fecha_planificada, a.fecha_real, a.get_estado_display(),
            str(labels[a.cumplimiento]), str(a.canal or ""), a.vocero, a.evidencia, a.indicador,
            "Sí" if a.no_planificada else "",
        ]])
    ws.freeze_panes = "C2"
    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = f'attachment; filename="ruta-{request.client.slug}.xlsx"'
    wb.save(response)
    return response
