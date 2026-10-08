"""Answering through a personal link. No account: the signed token identifies the person."""

from django.db import IntegrityError, transaction
from django.http import Http404
from django.shortcuts import render
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.clickjacking import xframe_options_deny

from apps.core.models import Module
from apps.core.tenancy import tenant_context

from . import scoring
from .models import Enlace, Respuesta, TipoPregunta


def _closed(request, enlace, message, status=410):
    return render(
        request,
        "formularios/publico_cerrado.html",
        {"enlace": enlace, "message": message},
        status=status,
    )


@never_cache
@xframe_options_deny
def responder(request, token):
    enlace = Enlace.from_token(token)
    if (
        enlace is None
        or not enlace.client.is_active
        or not enlace.client.has_module(Module.FORMULARIOS)
        or not enlace.persona.is_active
    ):
        raise Http404
    with tenant_context(enlace.client):
        c = enlace.cuestionario
        if not c.is_open:
            return _closed(request, enlace, _("Este cuestionario ya no recibe respuestas."))
        usados = enlace.intentos_usados()
        if usados >= c.intentos:
            ultima = enlace.respuestas.order_by("-enviada_at").first()
            return render(
                request,
                "formularios/publico_resultado.html",
                {"enlace": enlace, "respuesta": ultima, "sin_intentos": True},
            )

        preguntas = list(c.preguntas.prefetch_related("opciones"))
        missing = []
        if request.method == "POST":
            elecciones = {}
            for p in preguntas:
                valid = {o.pk for o in p.opciones.all()}
                chosen = {int(v) for v in request.POST.getlist(f"p{p.pk}") if v.isdigit()}
                chosen &= valid
                if p.tipo != TipoPregunta.MULTIPLE:
                    chosen = set(list(chosen)[:1])
                if not chosen:
                    missing.append(p.pk)
                elecciones[p.pk] = chosen
                for o in p.opciones.all():  # keep the answers if the form is shown again
                    o.checked = o.pk in chosen
            if not missing:
                per_q, total, passed = scoring.grade(c, elecciones)
                try:
                    with transaction.atomic():
                        respuesta = Respuesta.objects.create(
                            enlace=enlace,
                            intento=usados + 1,
                            elecciones={str(k): sorted(v) for k, v in elecciones.items()},
                            puntos_por_pregunta={str(k): str(v) for k, v in per_q.items()},
                            puntaje=total,
                            aprobado=passed,
                        )
                except IntegrityError:  # double submit
                    respuesta = enlace.respuestas.get(intento=usados + 1)
                return render(
                    request,
                    "formularios/publico_resultado.html",
                    {
                        "enlace": enlace,
                        "respuesta": respuesta,
                        "restantes": c.intentos - respuesta.intento,
                    },
                )
        return render(
            request,
            "formularios/publico_responder.html",
            {
                "enlace": enlace,
                "c": c,
                "preguntas": preguntas,
                "missing": missing,
                "intento": usados + 1,
            },
        )
