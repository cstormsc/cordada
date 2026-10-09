import csv

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST
from openpyxl import Workbook
from openpyxl.styles import Font

from apps.core.decorators import client_member_required
from apps.core.models import Module
from apps.core.permissions import Action, role_actions
from apps.matriz.export import safe_cell

from . import importer, results, scoring, supervisores
from .forms import (
    TIPO_HELP,
    CargaForm,
    CuestionarioForm,
    EnlacesForm,
    PreguntaForm,
    ResultadosForm,
    opcion_formset,
    parse_points,
)
from .models import Cuestionario, Enlace, EstadoCuestionario, Persona, Pregunta, TipoPregunta

A = Action
SESSION_KEY = "formularios_carga"


def _actions(request):
    if not request.client.has_module(Module.FORMULARIOS):
        return frozenset()
    return role_actions(request.membership.role, Module.FORMULARIOS)


def _require(request, *any_of):
    if not set(any_of) & _actions(request):
        raise PermissionDenied


def _cuestionario(numero):
    return get_object_or_404(Cuestionario.objects.select_related("impacto"), numero=numero)


def _editor_url(client_slug, numero):
    return reverse(
        "formularios:cuestionario", kwargs={"client_slug": client_slug, "numero": numero}
    )


@client_member_required
def index(request, client_slug):
    actions = _actions(request)
    if not actions & {A.EDIT, A.DESIGN}:
        raise PermissionDenied
    cuestionarios = Cuestionario.objects.select_related("impacto").annotate(
        n_preguntas=Count("preguntas", distinct=True), n_enlaces=Count("enlaces", distinct=True)
    )
    return render(
        request,
        "formularios/index.html",
        {
            "cuestionarios": cuestionarios,
            "can_people": A.EDIT in actions,
            "personas": Persona.objects.filter(is_active=True).count()
            if A.EDIT in actions
            else None,
        },
    )


# --- People ---


@client_member_required
def personas(request, client_slug):
    _require(request, A.EDIT)
    q = request.GET.get("q", "").strip()
    qs = Persona.objects.select_related("grupo")
    if q:
        qs = qs.filter(
            Q(email__icontains=q)
            | Q(nombre__icontains=q)
            | Q(apellido__icontains=q)
            | Q(departamento__icontains=q)
        )
    if request.GET.get("inactivas") != "1":
        qs = qs.filter(is_active=True)
    from .models import Carga

    return render(
        request,
        "formularios/personas.html",
        {
            "personas": qs[:500],
            "total": qs.count(),
            "q": q,
            "por_grupo": Persona.objects.filter(is_active=True)
            .values("grupo__name")
            .annotate(n=Count("id"))
            .order_by("grupo__name"),
            "cargas": Carga.objects.select_related("creada_por")[:5],
            "supervisores": [
                s
                for s in supervisores.from_people(request.client, Persona.objects.all())
                if s.estado != supervisores.OK
            ],
        },
    )


@client_member_required
@require_POST
def persona_estado(request, client_slug, pk):
    _require(request, A.EDIT)
    persona = get_object_or_404(Persona.objects, pk=pk)
    persona.is_active = not persona.is_active
    persona.save(update_fields=["is_active"])
    return redirect("formularios:personas", client_slug=client_slug)


@client_member_required
def cargar(request, client_slug):
    """Step 1: upload and preview. Step 2 (confirmar) applies what is kept in the session."""
    _require(request, A.EDIT)
    form = CargaForm(request.POST or None, request.FILES or None)
    preview = None
    if request.method == "POST" and form.is_valid():
        archivo = form.cleaned_data["archivo"]
        try:
            headers, rows = importer.read_rows(archivo)
            mapping = importer.map_headers(headers)
            records, errors = importer.parse(rows, mapping)
        except importer.PeopleImportError as e:
            form.add_error("archivo", str(e))
        else:
            group_field = form.cleaned_data["columna_grupo"]
            if group_field and group_field not in mapping:
                form.add_error("columna_grupo", _("El archivo no tiene esa columna."))
            else:
                existing = set(
                    Persona.objects.filter(email__in=[r["email"] for r in records]).values_list(
                        "email", flat=True
                    )
                )
                preview = _preview(records, errors, existing, mapping, group_field)
                preview["supervisores"] = supervisores.from_records(request.client, records)
                request.session[SESSION_KEY] = {
                    "filename": archivo.name,
                    "records": records,
                    "errors": errors,
                    "group_field": group_field,
                    "create_groups": form.cleaned_data["crear_grupos"],
                }
    return render(request, "formularios/cargar.html", {"form": form, "preview": preview})


def _preview(records, errors, existing, mapping, group_field):
    from apps.catalogs.models import GrupoImpactado

    groups = {g.name.lower() for g in GrupoImpactado.objects.all()}
    values = {}
    if group_field:
        for r in records:
            name = " ".join(r.get(group_field, "").split())
            if name:
                values[name] = name.lower() in groups
    return {
        "total": len(records),
        "nuevas": len(records) - len(existing),
        "actualizadas": len(existing),
        "errores": errors,
        "columnas": sorted(mapping),
        "muestra": records[:5],
        "grupos": sorted(values.items()),
    }


@client_member_required
@require_POST
def confirmar_carga(request, client_slug):
    _require(request, A.EDIT)
    data = request.session.pop(SESSION_KEY, None)
    if not data:
        messages.error(request, _("La vista previa expiró. Sube el archivo de nuevo."))
        return redirect("formularios:cargar", client_slug=client_slug)
    carga = importer.apply(
        data["records"],
        filename=data["filename"],
        user=request.user,
        group_field=data["group_field"],
        create_groups=data["create_groups"],
        errors=data["errors"],
    )
    messages.success(
        request,
        _("Carga lista: %(c)s personas nuevas y %(a)s actualizadas.")
        % {"c": carga.creadas, "a": carga.actualizadas},
    )
    return redirect("formularios:personas", client_slug=client_slug)


# --- Questionnaires ---


@client_member_required
def crear(request, client_slug):
    _require(request, A.DESIGN)
    form = CuestionarioForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        c = form.save(commit=False)
        c.creado_por = request.user
        c.save()
        return redirect("formularios:cuestionario", client_slug=client_slug, numero=c.numero)
    return render(request, "formularios/cuestionario_form.html", {"form": form})


@client_member_required
def editar(request, client_slug, numero):
    _require(request, A.DESIGN)
    c = _cuestionario(numero)
    form = CuestionarioForm(request.POST or None, instance=c)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Cambios guardados."))
        return redirect("formularios:cuestionario", client_slug=client_slug, numero=numero)
    return render(request, "formularios/cuestionario_form.html", {"form": form, "c": c})


@client_member_required
def cuestionario(request, client_slug, numero):
    actions = _actions(request)
    if not actions & {A.EDIT, A.DESIGN}:
        raise PermissionDenied
    c = _cuestionario(numero)
    preguntas = list(c.preguntas.prefetch_related("opciones"))
    return render(
        request,
        "formularios/cuestionario.html",
        {
            "c": c,
            "preguntas": preguntas,
            "total": c.total_puntos(),
            "errors": scoring.publish_errors(c) if c.is_draft else [],
            "can_design": A.DESIGN in actions,
            "can_links": A.EDIT in actions,
            "totales": results.totals(c) if not c.is_draft else None,
        },
    )


def _draft_or_redirect(request, c, client_slug):
    if not c.is_draft:
        messages.error(request, _("El cuestionario ya está publicado: no se puede modificar."))
        return redirect("formularios:cuestionario", client_slug=client_slug, numero=c.numero)
    return None


@client_member_required
def pregunta(request, client_slug, numero, pk=None):
    _require(request, A.DESIGN)
    c = _cuestionario(numero)
    if (resp := _draft_or_redirect(request, c, client_slug)) is not None:
        return resp
    p = (
        get_object_or_404(Pregunta.objects, cuestionario=c, pk=pk)
        if pk
        else Pregunta(cuestionario=c, orden=c.preguntas.count() + 1)
    )
    form = PreguntaForm(request.POST or None, instance=p)
    formset = opcion_formset(p, request.POST or None)
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        with transaction.atomic():
            is_new = p.pk is None
            p = form.save()
            formset.instance = p
            formset.save()
            if p.tipo == TipoPregunta.SI_NO and not p.opciones.exists():
                p.opciones.create(texto=_("Sí"), orden=1, correcta=True)
                p.opciones.create(texto=_("No"), orden=2)
            if is_new and not c.puntos_manuales:
                scoring.redistribute(c)
        return redirect(f"{_editor_url(client_slug, numero)}#p{p.pk}")
    return render(
        request,
        "formularios/pregunta_form.html",
        {
            "c": c,
            "p": p,
            "form": form,
            "formset": formset,
            "tipo_help": TIPO_HELP,
        },
    )


@client_member_required
@require_POST
def borrar_pregunta(request, client_slug, numero, pk):
    _require(request, A.DESIGN)
    c = _cuestionario(numero)
    if (resp := _draft_or_redirect(request, c, client_slug)) is not None:
        return resp
    get_object_or_404(Pregunta.objects, cuestionario=c, pk=pk).delete()
    for i, p in enumerate(c.preguntas.all(), start=1):
        if p.orden != i:
            p.orden = i
            p.save(update_fields=["orden"])
    if not c.puntos_manuales:
        scoring.redistribute(c)
    messages.success(request, _("Pregunta eliminada."))
    return redirect("formularios:cuestionario", client_slug=client_slug, numero=numero)


@client_member_required
@require_POST
def puntos(request, client_slug, numero):
    """Saves hand-edited points; from then on the questionnaire keeps them."""
    _require(request, A.DESIGN)
    c = _cuestionario(numero)
    if (resp := _draft_or_redirect(request, c, client_slug)) is not None:
        return resp
    preguntas = list(c.preguntas.all())
    try:
        values = parse_points(request.POST, preguntas)
    except ValueError as e:
        messages.error(request, str(e))
    else:
        with transaction.atomic():
            for p, value in values.items():
                if p.puntos != value:
                    p.puntos = value
                    p.save(update_fields=["puntos"])
            c.puntos_manuales = True
            c.save(update_fields=["puntos_manuales"])
        total = c.total_puntos()
        if total == scoring.TOTAL_POINTS:
            messages.success(request, _("Puntos guardados."))
        else:
            messages.warning(
                request,
                _("Puntos guardados. Suman %(t)s: ajústalos a 100 antes de publicar.")
                % {"t": total},
            )
    return redirect(f"{_editor_url(client_slug, numero)}#puntos")


@client_member_required
@require_POST
def repartir(request, client_slug, numero):
    _require(request, A.DESIGN)
    c = _cuestionario(numero)
    if (resp := _draft_or_redirect(request, c, client_slug)) is not None:
        return resp
    with transaction.atomic():
        scoring.redistribute(c)
        c.puntos_manuales = False
        c.save(update_fields=["puntos_manuales"])
    messages.success(request, _("Puntos repartidos en partes iguales."))
    return redirect(f"{_editor_url(client_slug, numero)}#puntos")


@client_member_required
@require_POST
def publicar(request, client_slug, numero):
    _require(request, A.DESIGN)
    c = _cuestionario(numero)
    if (resp := _draft_or_redirect(request, c, client_slug)) is not None:
        return resp
    if errors := scoring.publish_errors(c):
        for e in errors:
            messages.error(request, e)
    else:
        c.estado, c.publicado_at = EstadoCuestionario.PUBLICADO, timezone.now()
        c.save(update_fields=["estado", "publicado_at"])
        messages.success(
            request, _("Publicado. Preguntas y puntos quedan fijos; ya puedes generar los enlaces.")
        )
    return redirect("formularios:cuestionario", client_slug=client_slug, numero=numero)


@client_member_required
@require_POST
def cerrar(request, client_slug, numero):
    _require(request, A.DESIGN)
    c = _cuestionario(numero)
    if c.estado == EstadoCuestionario.PUBLICADO:
        c.estado = EstadoCuestionario.CERRADO
        c.save(update_fields=["estado"])
        messages.success(request, _("Cuestionario cerrado: ya no acepta respuestas."))
    return redirect("formularios:cuestionario", client_slug=client_slug, numero=numero)


# --- Links ---


@client_member_required
def enlaces(request, client_slug, numero):
    _require(request, A.EDIT)
    c = _cuestionario(numero)
    if c.is_draft:
        messages.error(request, _("Publica el cuestionario antes de generar enlaces."))
        return redirect("formularios:cuestionario", client_slug=client_slug, numero=numero)
    form = EnlacesForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        personas = Persona.objects.filter(is_active=True)
        if grupos := form.cleaned_data["grupos"]:
            personas = personas.filter(grupo__in=grupos)
        have = set(c.enlaces.values_list("persona_id", flat=True))
        nuevas = [p for p in personas if p.pk not in have]
        with transaction.atomic():
            for p in nuevas:
                Enlace.objects.create(cuestionario=c, persona=p)
        messages.success(
            request, _("%(n)s enlaces nuevos (cada persona tiene uno solo).") % {"n": len(nuevas)}
        )
        return redirect("formularios:enlaces", client_slug=client_slug, numero=numero)
    return render(
        request,
        "formularios/enlaces.html",
        {
            "c": c,
            "form": form,
            "n_enlaces": c.enlaces.count(),
            "enlace_dias": Enlace.validez().days,
            "por_grupo": c.enlaces.values("persona__grupo__name")
            .annotate(n=Count("id"))
            .order_by("persona__grupo__name"),
        },
    )


@client_member_required
def exportar_enlaces(request, client_slug, numero):
    """§7.3: first phase exports the links so the client sends them from its own email."""
    _require(request, A.EDIT)
    c = _cuestionario(numero)
    fmt = request.GET.get("formato", "xlsx")
    vence = timezone.localdate() + Enlace.validez()
    if c.vence:
        vence = min(vence, c.vence)
    rows = [
        [
            e.persona.email,
            e.persona.nombre,
            e.persona.apellido,
            str(e.persona.grupo or ""),
            request.build_absolute_uri(reverse("formularios_responder", args=[e.token])),
            vence.isoformat(),
        ]
        for e in c.enlaces.select_related("persona", "persona__grupo").order_by("persona__email")
    ]
    headers = ["correo", "nombre", "apellido", "grupo", "enlace", "vence"]
    filename = f"enlaces-{c.codigo.lower()}-{request.client.slug}"
    if fmt == "csv":
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{filename}.csv"'
        response.write("﻿")  # Excel opens UTF-8 CSV correctly with a BOM
        writer = csv.writer(response)
        writer.writerow(headers)
        writer.writerows([[safe_cell(v) for v in row] for row in rows])
        return response
    wb = Workbook()
    ws = wb.active
    ws.title = "Enlaces"
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for row in rows:
        ws.append([safe_cell(v) for v in row])
    ws.column_dimensions["D"].width = 80
    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}.xlsx"'
    wb.save(response)
    return response


# --- Results ---


@client_member_required
def resultados(request, client_slug, numero):
    actions = _actions(request)
    if not actions & {A.EDIT, A.DESIGN}:
        raise PermissionDenied
    c = _cuestionario(numero)
    individual = A.VIEW_INDIVIDUAL in actions
    # Crossing two groupings (e.g. an office minus a group) gives hidden groups back, so
    # only those who already see individual results can change the grouping.
    form = ResultadosForm(request.GET or None) if individual else None
    por = form.cleaned_data.get("por") if form and form.is_valid() else ""
    min_size = request.client.tamano_minimo_grupo
    return render(
        request,
        "formularios/resultados.html",
        {
            "c": c,
            "form": form,
            "min_size": min_size,
            "totales": results.totals(c),
            "agregado": results.aggregate(c, by=por or "grupo", min_size=min_size),
            "por_pregunta": results.per_question(c, min_size=min_size),
            "individual": results.individual(c) if individual else None,
        },
    )
