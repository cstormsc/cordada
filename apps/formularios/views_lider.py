"""Leader's practical evaluation (§7.5): checklists (guides), evaluation (leaders), follow-up."""

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.core.attachments import file_response
from apps.core.decorators import client_member_required
from apps.matriz.models import Estado, Impacto

from . import certificacion
from .forms import ActaForm, CriterioForm, ListaForm
from .models import Acta, Criterio, EstadoCertificacion, EstadoLista, ListaObservacion
from .views import A, _actions, _require


def _lista(pk):
    return get_object_or_404(
        ListaObservacion.objects.select_related("impacto", "impacto__grupo"), pk=pk
    )


# --- Checklists (training team) ---


@client_member_required
def listas(request, client_slug):
    _require(request, A.DESIGN, A.EDIT)
    impactos = (
        Impacto.objects.filter(requiere_certificacion_lider=True)
        .exclude(estado=Estado.DESCARTADO)
        .select_related("grupo")
        .order_by("numero")
    )
    rows = []
    for i in impactos:
        lista = getattr(i, "lista_observacion", None)
        rows.append(
            {
                "impacto": i,
                "lista": lista,
                "resumen": certificacion.summary(lista) if lista else None,
            }
        )
    return render(
        request,
        "formularios/listas.html",
        {"rows": rows, "can_design": A.DESIGN in _actions(request)},
    )


@client_member_required
def lista_crear(request, client_slug, impacto):
    _require(request, A.DESIGN)
    impacto = get_object_or_404(Impacto.objects, numero=impacto, requiere_certificacion_lider=True)
    if hasattr(impacto, "lista_observacion"):
        return redirect(
            "formularios:lista", client_slug=client_slug, pk=impacto.lista_observacion.pk
        )
    form = ListaForm(
        request.POST or None,
        initial={"titulo": _("Observación práctica · %(t)s") % {"t": impacto.titulo}},
    )
    if request.method == "POST" and form.is_valid():
        lista = form.save(commit=False)
        lista.impacto, lista.creada_por = impacto, request.user
        lista.save()
        return redirect("formularios:lista", client_slug=client_slug, pk=lista.pk)
    return render(request, "formularios/lista_form.html", {"form": form, "impacto": impacto})


@client_member_required
def lista(request, client_slug, pk):
    _require(request, A.DESIGN, A.EDIT)
    lista = _lista(pk)
    can_design = A.DESIGN in _actions(request) and lista.is_draft
    form = ListaForm(request.POST or None, instance=lista) if can_design else None
    criterio_form = CriterioForm(request.POST or None, prefix="c") if can_design else None
    if request.method == "POST" and can_design:
        if "c-texto" in request.POST and criterio_form.is_valid():
            c = criterio_form.save(commit=False)
            c.lista, c.orden = lista, lista.criterios.count() + 1
            c.save()
            return redirect("formularios:lista", client_slug=client_slug, pk=pk)
        if "titulo" in request.POST and form.is_valid():
            form.save()
            messages.success(request, _("Cambios guardados."))
            return redirect("formularios:lista", client_slug=client_slug, pk=pk)
    return render(
        request,
        "formularios/lista.html",
        {
            "lista": lista,
            "form": form,
            "criterio_form": criterio_form,
            "criterios": lista.criterios.all(),
            "can_design": can_design,
        },
    )


@client_member_required
@require_POST
def criterio_borrar(request, client_slug, pk, criterio):
    _require(request, A.DESIGN)
    lista = _lista(pk)
    if lista.is_draft:
        get_object_or_404(Criterio.objects, lista=lista, pk=criterio).delete()
    return redirect("formularios:lista", client_slug=client_slug, pk=pk)


@client_member_required
@require_POST
def lista_publicar(request, client_slug, pk):
    _require(request, A.DESIGN)
    lista = _lista(pk)
    if not lista.criterios.exists():
        messages.error(request, _("Agrega al menos un criterio."))
    elif lista.is_draft:
        lista.estado = EstadoLista.PUBLICADA
        lista.save(update_fields=["estado"])
        messages.success(request, _("Lista publicada: los líderes ya pueden evaluar."))
    return redirect("formularios:lista", client_slug=client_slug, pk=pk)


@client_member_required
def seguimiento(request, client_slug, pk):
    """Progress by leader. Names: change team (all), guides (only en refuerzo)."""
    actions = _actions(request)
    _require(request, A.DESIGN, A.EDIT)
    lista = _lista(pk)
    evaluaciones = lista.evaluaciones.select_related("persona", "lider").order_by(
        "lider__email", "persona__nombre"
    )
    leaders = {}
    for ev in evaluaciones:
        row = leaders.setdefault(ev.lider, dict.fromkeys(EstadoCertificacion.values, 0))
        row[ev.estado] += 1
    individual = A.VIEW_INDIVIDUAL in actions
    return render(
        request,
        "formularios/seguimiento.html",
        {
            "lista": lista,
            "resumen": certificacion.summary(lista),
            "leaders": leaders.items(),
            "evaluaciones": evaluaciones if individual else None,
            "refuerzo": evaluaciones.filter(estado=EstadoCertificacion.EN_REFUERZO)
            if individual or A.DESIGN in actions
            else None,
            "actas": lista.actas.select_related("lider"),
        },
    )


@client_member_required
def acta_descargar(request, client_slug, pk, acta):
    actions = _actions(request)
    lista = _lista(pk)
    acta = get_object_or_404(Acta.objects, lista=lista, pk=acta)
    if not (A.EDIT in actions or A.DESIGN in actions or acta.lider_id == request.user.pk):
        raise PermissionDenied
    return file_response(acta)


# --- Leader ---


def _leader_lista(request, pk):
    if A.LEADER_EVAL not in _actions(request):
        raise PermissionDenied
    lista = _lista(pk)
    if lista.is_draft:
        raise Http404
    return lista


@client_member_required
def evaluar_index(request, client_slug):
    if A.LEADER_EVAL not in _actions(request):
        raise PermissionDenied
    rows = []
    for lista in ListaObservacion.objects.filter(estado=EstadoLista.PUBLICADA).select_related(
        "impacto"
    ):
        n = certificacion.team(lista, request.user.email).count()
        if n:
            mine = lista.evaluaciones.filter(lider=request.user)
            rows.append(
                {
                    "lista": lista,
                    "equipo": n,
                    "hechas": mine.exclude(estado=EstadoCertificacion.PENDIENTE).count(),
                }
            )
    return render(request, "formularios/evaluar_index.html", {"rows": rows})


@client_member_required
def evaluar(request, client_slug, pk):
    lista = _leader_lista(request, pk)
    criterios = list(lista.criterios.all())
    ids = [c.pk for c in criterios]
    evaluaciones = certificacion.evaluations_for(lista, request.user)
    if request.method == "POST":
        with transaction.atomic():
            for ev in evaluaciones:
                resultados = {}
                for cid in ids:
                    value = request.POST.get(f"e{ev.pk}-c{cid}")
                    if value in ("si", "no"):
                        resultados[cid] = value == "si"
                obs = request.POST.get(f"e{ev.pk}-obs")
                if resultados or obs is not None:
                    certificacion.save_results(
                        ev, resultados, obs.strip() if obs is not None else None, ids
                    )
        messages.success(request, _("Evaluación guardada."))
        return redirect("formularios:evaluar", client_slug=client_slug, pk=pk)
    for ev in evaluaciones:
        ev.cells = [(c, ev.resultados.get(str(c.pk))) for c in criterios]
        ev.editable = ev.estado in certificacion.EDITABLE
    pendientes_firma = [e for e in evaluaciones if e.estado == EstadoCertificacion.APLICADO]
    return render(
        request,
        "formularios/evaluar.html",
        {
            "lista": lista,
            "criterios": criterios,
            "evaluaciones": evaluaciones,
            "pendientes_firma": pendientes_firma,
            "faltan": [e for e in evaluaciones if e.estado == EstadoCertificacion.PENDIENTE],
            "acta_form": ActaForm(),
            "actas": lista.actas.filter(lider=request.user),
        },
    )


@client_member_required
def evaluar_pdf(request, client_slug, pk):
    """Pre-filled summary for the leader to print and sign."""
    lista = _leader_lista(request, pk)
    criterios = list(lista.criterios.all())
    ids = [c.pk for c in criterios]
    evaluaciones = [
        ev
        for ev in certificacion.evaluations_for(lista, request.user)
        if ev.estado == EstadoCertificacion.APLICADO
    ]
    for ev in evaluaciones:
        ev.cells = [ev.resultados.get(str(c.pk)) for c in criterios]
        ev.certifica = ev.cumple_todo(ids)
    from weasyprint import HTML

    html = render_to_string(
        "formularios/evaluar_pdf.html",
        {
            "lista": lista,
            "criterios": criterios,
            "evaluaciones": evaluaciones,
            "lider": request.user,
            "fecha": timezone.localdate(),
            "certificados": sum(1 for e in evaluaciones if e.certifica),
            "refuerzo": sum(1 for e in evaluaciones if not e.certifica),
        },
        request=request,
    )
    pdf = HTML(string=html, base_url=request.build_absolute_uri("/")).write_pdf()
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = (
        f'attachment; filename="evaluacion-{lista.impacto.codigo.lower()}-'
        f'{timezone.localdate():%Y%m%d}.pdf"'
    )
    return response


@client_member_required
@require_POST
def evaluar_acta(request, client_slug, pk):
    lista = _leader_lista(request, pk)
    if not lista.evaluaciones.filter(
        lider=request.user, estado=EstadoCertificacion.APLICADO
    ).exists():
        messages.error(request, _("No hay evaluaciones aplicadas pendientes de firma."))
        return redirect("formularios:evaluar", client_slug=client_slug, pk=pk)
    form = ActaForm(request.POST, request.FILES)
    if not form.is_valid():
        for errors in form.errors.values():
            for e in errors:
                messages.error(request, e)
        return redirect("formularios:evaluar", client_slug=client_slug, pk=pk)
    _acta, refuerzo = certificacion.register_signed_summary(
        lista, request.user, form, notify_request=request
    )
    messages.success(request, _("Resumen firmado registrado."))
    if refuerzo:
        messages.info(
            request,
            _("%(n)s persona(s) quedan en refuerzo; se avisó a los guías.") % {"n": len(refuerzo)},
        )
    return redirect("formularios:evaluar", client_slug=client_slug, pk=pk)
