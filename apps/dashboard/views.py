import json

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.core.decorators import client_member_required, client_permission_required
from apps.core.models import Module, Role
from apps.core.permissions import Action, can

from . import indicators as ind
from . import layout as dash_layout
from .forms import FiltroForm, IndicadorConfigForm, ValorManualForm
from .models import IndicadorConfig, Preferencia, ValorManual

DATA_ROLES = (Role.ADMINISTRACION, Role.EQUIPO_CAMBIO)


def _can_view(request):
    return can(
        request.user, request.client, Module.DASHBOARD, Action.VIEW, membership=request.membership
    )


def _can_load(request):
    return _can_view(request) and request.membership.role in DATA_ROLES


@client_member_required
@require_POST
def guardar_layout(request, client_slug):
    """Saves how this person arranged their dashboard; {"reset": true} goes back to default."""
    if not _can_view(request):
        raise PermissionDenied
    try:
        data = json.loads(request.body or b"{}")
    except ValueError:
        return HttpResponseBadRequest()
    if not isinstance(data, dict):
        return HttpResponseBadRequest()
    if data.get("reset"):
        Preferencia.objects.filter(usuario=request.user).delete()
        return JsonResponse({"ok": True, "layout": dash_layout.DEFAULT})
    layout = dash_layout.clean(data)
    Preferencia.objects.update_or_create(usuario=request.user, defaults={"layout": layout})
    return JsonResponse({"ok": True, "layout": dash_layout.resolve(layout)})


@client_member_required
def index(request, client_slug):
    if not _can_view(request):
        raise PermissionDenied
    filtro = FiltroForm(request.GET or None)
    params = filtro.cleaned_data if filtro.is_valid() else {}
    ctx = ind.Ctx(request.client, tiempo=params.get("tiempo"), grupo=params.get("grupo"))
    tiles = ind.tiles(ctx)
    frentes = {
        code: (label, [t for t in tiles if t.indicator.frente == code])
        for code, label in ind.FRENTES
    }
    general = next((t for t in tiles if t.indicator.key == ind.GENERAL), None)
    readiness = ind.readiness_by_group(ctx)
    verde, amarillo = ind.threshold("tr_preparacion")

    def module(mod):
        m = {"id": mod, "label": dash_layout.MODULES[mod], "template": f"dashboard/mod/{mod}.html"}
        if mod in frentes:
            m["template"], (m["nombre"], m["tiles"]) = "dashboard/mod/frente.html", frentes[mod]
            m["empty"] = not m["tiles"]
        if mod == "avance":
            m["tile"], m["empty"] = general, general is None  # deactivated in configuration
        return m

    saved = Preferencia.objects.filter(usuario=request.user).values_list("layout", flat=True)
    arrangement = dash_layout.resolve(saved.first())
    columns = {
        col: [m for m in map(module, arrangement[col]) if not m.get("empty")]
        for col in ("main", "side")
    }
    return render(
        request,
        "dashboard/index.html",
        {
            "filtro": filtro,
            "columns": columns,
            "hidden": [(mod, dash_layout.MODULES[mod]) for mod in arrangement["hidden"]],
            "niveles": ind.NIVELES,
            "alerts": ind.alerts(ctx),
            "can_view_matrix": can(
                request.user,
                request.client,
                Module.MATRIZ,
                Action.VIEW,
                membership=request.membership,
            ),
            "can_load": _can_load(request),
            "can_configure_indicators": can(
                request.user,
                request.client,
                Module.DASHBOARD,
                Action.EDIT,
                membership=request.membership,
            ),
            "chart_readiness": {
                "rows": [
                    {
                        "label": r["grupo"].name,
                        "value": float(r["value"]) if r["value"] is not None else None,
                    }
                    for r in readiness
                ],
                "threshold": float(amarillo) if amarillo is not None else None,
            },
            "readiness": readiness,
            "chart_tickets": ind.tickets_by_type(ctx),
            "querystring": request.GET.urlencode(),
        },
    )


@client_member_required
def datos(request, client_slug):
    """Manual data (§8): values that do not come from the platform."""
    if not _can_load(request):
        raise PermissionDenied
    form = ValorManualForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        valor = form.save(commit=False)
        valor.cargado_por = request.user
        valor.save()
        messages.success(request, _("Dato guardado."))
        return redirect("dashboard:datos", client_slug=client_slug)
    return render(
        request,
        "dashboard/datos.html",
        {
            "form": form,
            "valores": ValorManual.objects.select_related("grupo", "cargado_por")[:100],
            "names": {i.key: i.nombre for i in ind.INDICATORS},
        },
    )


@client_member_required
@require_POST
def borrar_dato(request, client_slug, pk):
    if not _can_load(request):
        raise PermissionDenied
    get_object_or_404(ValorManual.objects, pk=pk).delete()
    messages.success(request, _("Dato eliminado."))
    return redirect("dashboard:datos", client_slug=client_slug)


@client_permission_required(Module.DASHBOARD, Action.EDIT)
def indicadores(request, client_slug):
    """Configuración → Indicadores: thresholds, owner, frequency, visibility."""
    existing = {c.key: c for c in IndicadorConfig.objects.all()}
    rows = []
    for i in ind.INDICATORS:
        instance = existing.get(i.key) or IndicadorConfig(
            key=i.key, verde=i.verde, amarillo=i.amarillo, frecuencia=str(i.frecuencia)
        )
        rows.append((i, IndicadorConfigForm(instance=instance, indicator=i, prefix=i.key)))
    return render(request, "dashboard/indicadores.html", {"rows": rows})


@client_permission_required(Module.DASHBOARD, Action.EDIT)
@require_POST
def indicador_guardar(request, client_slug, key):
    i = ind.BY_KEY.get(key)
    if i is None:
        raise PermissionDenied
    instance = IndicadorConfig.objects.filter(key=key).first() or IndicadorConfig(key=key)
    form = IndicadorConfigForm(request.POST, instance=instance, indicator=i, prefix=key)
    if form.is_valid():
        form.save()
        messages.success(request, _("«%(n)s» actualizado.") % {"n": i.nombre})
    else:
        for errors in form.errors.values():
            for e in errors:
                messages.error(request, f"{i.nombre}: {e}")
    return redirect(f"/c/{client_slug}/dashboard/indicadores/#{key}")
