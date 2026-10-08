from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Case, IntegerField, Value, When
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST
from openpyxl import Workbook
from openpyxl.styles import Font

from apps.catalogs.models import SystemCatalog, SystemCatalogItem
from apps.core.decorators import client_member_required
from apps.core.models import Module
from apps.core.permissions import Action, can, role_actions
from apps.matriz.export import safe_cell
from apps.matriz.models import Impacto

from . import metrics, workflow
from .forms import CasoClienteForm, ComentarioForm, FiltroForm, MetricasForm, TicketForm
from .models import EstadoTicket, Ticket, TicketComentario, Urgencia

A = Action


def _actions(request):
    if not request.client.has_module(Module.BITACORA):
        return frozenset()
    return role_actions(request.membership.role, Module.BITACORA)


def _sees_all(actions):
    return A.VIEW in actions


def _visible(request):
    actions = _actions(request)
    if _sees_all(actions):
        return Ticket.objects.all()
    if A.REGISTER in actions:
        return Ticket.objects.filter(registrado_por=request.user)
    raise PermissionDenied


def _get(request, numero):
    return get_object_or_404(
        _visible(request).select_related(
            "categoria", "grupo", "impacto", "registrado_por", "recurrente_de", "validado_por"
        ),
        numero=numero,
    )


def _sees_matrix(request):
    return can(request.user, request.client, Module.MATRIZ, A.VIEW, membership=request.membership)


def _form_kwargs(request):
    actions = _actions(request)
    return {"classify": A.CLASSIFY in actions, "see_matrix": _sees_matrix(request)}


URGENT_FIRST = Case(
    When(urgencia=Urgencia.GRAVE, then=Value(0)), default=Value(1), output_field=IntegerField()
)


@client_member_required
def index(request, client_slug):
    actions = _actions(request)
    tickets = _visible(request)
    filtro = FiltroForm(request.GET or None)
    return render(
        request,
        "bitacora/index.html",
        {
            "filtro": filtro,
            "tickets": filtro.filter(tickets).select_related("categoria", "grupo"),
            "sees_all": _sees_all(actions),
            "can_register": A.REGISTER in actions,
            "sees_ti": A.EDIT_DERIVED in actions,
            "querystring": request.GET.urlencode(),
            "resumen": {
                "nuevos": tickets.filter(estado=EstadoTicket.NUEVO).count(),
                "en_ti": tickets.filter(estado=EstadoTicket.DERIVADO_TI).count(),
                "sin_validar": tickets.filter(validado=False)
                .exclude(
                    estado__in=[
                        EstadoTicket.NUEVO,
                        EstadoTicket.EN_CLASIFICACION,
                        EstadoTicket.CERRADO,
                    ]
                )
                .count(),
            }
            if _sees_all(actions)
            else None,
        },
    )


@client_member_required
def crear(request, client_slug):
    if A.REGISTER not in _actions(request):
        raise PermissionDenied
    own_groups = request.membership.grupos.filter(is_active=True)
    initial = {"grupo": own_groups.first()} if own_groups.count() == 1 else {}
    form = TicketForm(request.POST or None, initial=initial, **_form_kwargs(request))
    if request.method == "POST" and form.is_valid():
        ticket = form.save(commit=False)
        ticket.registrado_por = request.user
        ticket.save()
        messages.success(request, _("%(codigo)s registrado.") % {"codigo": ticket.codigo})
        if ticket.urgencia == Urgencia.GRAVE and ticket.es_tecnico:
            messages.warning(
                request,
                _(
                    "Fallo grave técnico: derívalo a TI ahora desde el "
                    "ticket y regístralo en la mesa de ayuda del cliente."
                ),
            )
        return redirect("bitacora:detalle", client_slug=client_slug, numero=ticket.numero)
    return render(request, "bitacora/form.html", {"form": form})


@client_member_required
def editar(request, client_slug, numero):
    actions = _actions(request)
    ticket = _get(request, numero)
    own_new = ticket.registrado_por_id == request.user.pk and ticket.estado == EstadoTicket.NUEVO
    if not (A.CLASSIFY in actions and ticket.estado != EstadoTicket.CERRADO) and not own_new:
        raise PermissionDenied
    form = TicketForm(request.POST or None, instance=ticket, **_form_kwargs(request))
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Cambios guardados."))
        return redirect("bitacora:detalle", client_slug=client_slug, numero=numero)
    return render(request, "bitacora/form.html", {"form": form, "ticket": ticket})


@client_member_required
def detalle(request, client_slug, numero):
    actions = _actions(request)
    ticket = _get(request, numero)
    own_new = ticket.registrado_por_id == request.user.pk and ticket.estado == EstadoTicket.NUEVO
    return render(
        request,
        "bitacora/detalle.html",
        {
            "ticket": ticket,
            "steps": workflow.available(ticket, actions),
            "can_validate": workflow.can_validate(ticket, actions),
            "can_edit": (A.CLASSIFY in actions and ticket.estado != EstadoTicket.CERRADO)
            or own_new,
            "caso_form": CasoClienteForm(instance=ticket)
            if A.EDIT_DERIVED in actions and ticket.es_tecnico
            else None,
            "comentario_form": ComentarioForm(),
            "can_propose": _can_propose(request, ticket),
            "sees_matrix": _sees_matrix(request),
            "transiciones": ticket.transiciones.select_related("usuario"),
            "comentarios": ticket.comentarios.select_related("autor"),
        },
    )


@client_member_required
@require_POST
def cambiar_estado(request, client_slug, numero):
    actions = _actions(request)
    ticket = _get(request, numero)
    try:
        workflow.transition(
            ticket,
            request.POST.get("hacia"),
            user=request.user,
            actions=actions,
            reason=request.POST.get("motivo", ""),
        )
        messages.success(
            request,
            _("%(codigo)s: %(estado)s.")
            % {"codigo": ticket.codigo, "estado": ticket.get_estado_display()},
        )
    except workflow.TicketError as e:
        for m in e.messages:
            messages.error(request, m)
    return redirect("bitacora:detalle", client_slug=client_slug, numero=numero)


@client_member_required
@require_POST
def validar(request, client_slug, numero):
    ticket = _get(request, numero)
    try:
        workflow.validate(ticket, user=request.user, actions=_actions(request))
        messages.success(request, _("Clasificación validada."))
    except workflow.TicketError as e:
        for m in e.messages:
            messages.error(request, m)
    return redirect("bitacora:detalle", client_slug=client_slug, numero=numero)


@client_member_required
@require_POST
def caso_cliente(request, client_slug, numero):
    if A.EDIT_DERIVED not in _actions(request):
        raise PermissionDenied
    ticket = _get(request, numero)
    form = CasoClienteForm(request.POST, instance=ticket)
    if form.is_valid():
        form.save()
        messages.success(request, _("Número de caso guardado."))
    return redirect("bitacora:detalle", client_slug=client_slug, numero=numero)


@client_member_required
@require_POST
def comentar(request, client_slug, numero):
    ticket = _get(request, numero)
    form = ComentarioForm(request.POST)
    if form.is_valid():
        TicketComentario.objects.create(
            ticket=ticket, autor=request.user, texto=form.cleaned_data["texto"]
        )
    url = reverse("bitacora:detalle", kwargs={"client_slug": client_slug, "numero": numero})
    return redirect(f"{url}#comentarios")


def _can_propose(request, ticket):
    if not ticket.es_impacto_no_anticipado or ticket.impacto_id:
        return False
    return any(
        can(request.user, request.client, Module.MATRIZ, a, membership=request.membership)
        for a in (A.PROPOSE, A.EDIT)
    )


@client_member_required
@require_POST
def proponer_impacto(request, client_slug, numero):
    """§6: an 'impacto no anticipado' ticket proposes an impact in the matrix."""
    ticket = _get(request, numero)
    if not _can_propose(request, ticket):
        raise PermissionDenied
    origen = (
        SystemCatalogItem.objects.of(SystemCatalog.ORIGEN)
        .filter(code="bitacora", is_active=True)
        .first()
    )
    impacto = Impacto.objects.create(
        titulo=ticket.titulo,
        descripcion=_("%(descripcion)s\n\n(Propuesto desde el ticket %(codigo)s de la Bitácora.)")
        % {"descripcion": ticket.descripcion, "codigo": ticket.codigo},
        grupo=ticket.grupo,
        origen=origen,
        registrado_por=request.user,
    )
    ticket.impacto = impacto
    ticket.save(update_fields=["impacto"])
    messages.success(
        request,
        _("%(impacto)s propuesto en la matriz desde %(ticket)s.")
        % {"impacto": impacto.codigo, "ticket": ticket.codigo},
    )
    return redirect("matriz:detalle", client_slug=client_slug, numero=impacto.numero)


@client_member_required
def ti(request, client_slug):
    """Live view for the technical team: tickets sent to IT, refreshed every few seconds."""
    if A.EDIT_DERIVED not in _actions(request):
        raise PermissionDenied
    tickets = (
        Ticket.objects.filter(estado=EstadoTicket.DERIVADO_TI)
        .select_related("categoria", "grupo", "registrado_por")
        .annotate(urgent_first=URGENT_FIRST)
        .order_by("urgent_first", "created_at")
    )
    context = {
        "tickets": tickets,
        "now": timezone.now(),
        "resueltos_hoy": Ticket.objects.filter(resuelto_at__date=timezone.localdate()).count(),
    }
    template = "bitacora/_ti_lista.html" if request.htmx else "bitacora/ti.html"
    return render(request, template, context)


@client_member_required
def metricas(request, client_slug):
    if A.VIEW not in _actions(request):
        raise PermissionDenied
    form = MetricasForm(request.GET or None)
    params = form.cleaned_data if form.is_valid() else {}
    return render(
        request,
        "bitacora/metricas.html",
        {
            "form": form,
            "m": metrics.metricas(desde=params.get("desde"), hasta=params.get("hasta")),
        },
    )


@client_member_required
def exportar(request, client_slug):
    if A.VIEW not in _actions(request):
        raise PermissionDenied
    filtro = FiltroForm(request.GET or None)
    tickets = filtro.filter(Ticket.objects.all()).select_related(
        "categoria", "grupo", "impacto", "registrado_por", "recurrente_de"
    )
    wb = Workbook()
    ws = wb.active
    ws.title = "Bitácora"
    ws.append(
        [
            "ID",
            "Asunto",
            "Categoría",
            "Urgencia",
            "Estado",
            "Validado",
            "Grupo",
            "Impacto",
            "Caso cliente",
            "Repite",
            "Registrado por",
            "Registrado",
            "Primera respuesta",
            "Resolución",
            "Cierre",
            "Descripción",
        ]
    )
    for cell in ws[1]:
        cell.font = Font(bold=True)

    def naive(dt):
        return timezone.localtime(dt).replace(tzinfo=None) if dt else None

    for t in tickets:
        ws.append(
            [
                safe_cell(v)
                for v in [
                    t.codigo,
                    t.titulo,
                    str(t.categoria),
                    t.get_urgencia_display(),
                    t.get_estado_display(),
                    "Sí" if t.validado else "No",
                    str(t.grupo or ""),
                    t.impacto.codigo if t.impacto else "",
                    t.caso_cliente,
                    t.recurrente_de.codigo if t.recurrente_de else "",
                    t.registrado_por.display_name,
                    naive(t.created_at),
                    naive(t.primera_respuesta_at),
                    naive(t.resuelto_at),
                    naive(t.cerrado_at),
                    t.descripcion,
                ]
            ]
        )
    ws.freeze_panes = "C2"
    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = f'attachment; filename="bitacora-{request.client.slug}.xlsx"'
    wb.save(response)
    return response
