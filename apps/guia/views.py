from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.catalogs.models import Scale, SystemCatalog, SystemCatalogItem
from apps.core.attachments import file_response
from apps.core.decorators import client_permission_required
from apps.core.models import Module
from apps.core.permissions import Action, can
from apps.scoring import rules

from . import anchors
from .forms import DocumentoForm
from .models import Documento, Plantilla, Tema

PREGUNTA = "Pregunta que responde:"


def _pregunta(help_text):
    """The question a tiempo answers, from its help (seeded from Parte A), or ""."""
    for line in help_text.splitlines():
        if line.startswith(PREGUNTA):
            return line.removeprefix(PREGUNTA).strip()
    return ""


def _catalogos():
    items = list(SystemCatalogItem.objects.active())
    for i in items:
        if i.catalog == SystemCatalog.TIEMPO:
            i.pregunta = _pregunta(i.help_text)
    catalogos = [
        {
            "code": code,
            "anchor": anchors.catalogo(code),
            "name": label,
            "items": [i for i in items if i.catalog == code],
        }
        for code, label in SystemCatalog.choices
    ]
    return [c for c in catalogos if c["items"]]


def _calculos(scales):
    """Risk bands and the priority matrix, computed from the same rules the app uses."""
    bands = [
        {
            "label": band.label,
            "scores": sorted(s for s in rules.POSSIBLE_SCORES if rules.risk_band(s) == band),
        }
        for band in rules.RiskBand
    ]
    magnitud = next((s for s in scales if s.code == "magnitud"), None)
    labels = {lvl.value: lvl.label for lvl in magnitud.levels.all()} if magnitud else {}
    magnitudes = [(m, labels.get(m, str(m))) for m in rules.SCALE_VALUES]
    matrix = [
        {
            "band": band.label,
            "cells": [rules.priority(m, band).name for m, _label in magnitudes],
        }
        for band in reversed(rules.RiskBand)
    ]
    return {
        "anchor": anchors.CALCULOS,
        "bands": bands,
        "magnitudes": [label for _m, label in magnitudes],
        "matrix": matrix,
        "priorities": [p.label for p in rules.Priority],
    }


def _can_edit(request):
    return can(
        request.user, request.client, Module.GUIA, Action.EDIT, membership=request.membership
    )


@client_permission_required(Module.GUIA, Action.VIEW)
def index(request, client_slug):
    scales = list(Scale.objects.prefetch_related("levels"))
    for scale in scales:
        scale.anchor = anchors.escala(scale.code)
    can_edit = _can_edit(request)
    return render(
        request,
        "guia/index.html",
        {
            "temas": Tema.objects.filter(is_active=True),
            "catalogos": _catalogos(),
            "escalas": scales,
            "calculos": _calculos(scales),
            "plantillas": Plantilla.objects.filter(is_active=True),
            "documentos": Documento.objects.select_related("subido_por"),
            "can_edit": can_edit,
            "documento_form": DocumentoForm() if can_edit else None,
        },
    )


@client_permission_required(Module.GUIA, Action.VIEW)
def descargar_plantilla(request, client_slug, pk):
    return file_response(get_object_or_404(Plantilla, is_active=True, pk=pk))


@client_permission_required(Module.GUIA, Action.VIEW)
def descargar_documento(request, client_slug, pk):
    return file_response(get_object_or_404(Documento.objects, pk=pk))


def _documentos_url(client_slug):
    return f"{reverse('guia:index', args=[client_slug])}#documentos"


@client_permission_required(Module.GUIA, Action.EDIT)
@require_POST
def agregar_documento(request, client_slug):
    form = DocumentoForm(request.POST, request.FILES)
    if form.is_valid():
        form.save_for(request.user)
        messages.success(request, _("Documento agregado."))
    else:
        for errors in form.errors.values():
            for e in errors:
                messages.error(request, e)
    return redirect(_documentos_url(client_slug))


@client_permission_required(Module.GUIA, Action.EDIT)
@require_POST
def eliminar_documento(request, client_slug, pk):
    documento = get_object_or_404(Documento.objects, pk=pk)
    if documento.archivo:
        documento.archivo.delete(save=False)
    documento.delete()
    messages.success(request, _("Documento eliminado."))
    return redirect(_documentos_url(client_slug))
