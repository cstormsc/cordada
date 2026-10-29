# ruff: noqa: E501 (the story is kept as one-row-per-record tables)
"""Demo client: a fictional bank replacing its core banking system ("Proyecto Núcleo").

Built by `manage.py seed_demo`. Every date is relative to the day it runs, so the story
(stages, overdue activities, recent tickets) reads right whenever it is rebuilt. People other
than the presenter are members without a password: they appear as names, nobody logs in as them.
"""

from datetime import timedelta
from decimal import Decimal

from django.apps import apps
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.utils import timezone

from apps.aprendizaje.avance import sincronizar
from apps.aprendizaje.cursos import publish_errors
from apps.aprendizaje.models import (
    Ajustes,
    Bloque,
    BloqueItem,
    Curso,
    Encabezado,
    EstadoCurso,
    Inscripcion,
    Leccion,
    LeccionVista,
    Montana,
)
from apps.bitacora import workflow as ticket_flow
from apps.bitacora.models import Ticket, TicketAfectado, TicketComentario, TicketTransicion
from apps.catalogs.models import (
    Canal,
    Cargo,
    CategoriaResponsable,
    GrupoImpactado,
    SystemCatalog,
    SystemCatalogItem,
    UnidadOrganizacional,
)
from apps.core.models import Client, Invitation, Membership, Module, Role, User
from apps.core.permissions import Action
from apps.core.tenancy import tenant_context
from apps.dashboard.indicators import INDICATORS
from apps.dashboard.models import IndicadorConfig, ValorManual
from apps.formularios import certificacion, scoring
from apps.formularios.forms import ActaForm
from apps.formularios.models import (
    Criterio,
    Cuestionario,
    Enlace,
    EstadoCuestionario,
    EstadoLista,
    ListaObservacion,
    Opcion,
    Persona,
    Pregunta,
    Respuesta,
    TipoPregunta,
)
from apps.guia.models import Documento
from apps.matriz import export, workflow
from apps.matriz.models import Adjunto, Comentario, Dependencia, Foto, Impacto, Transicion
from apps.ruta.models import Actividad, Evidencia

SLUG = "demo"
NAME = "Banco Altiplano (demo)"
DOMAIN = "demo-altiplano.example"  # .example never delivers mail

U = UnidadOrganizacional.Kind


# --- Helpers -----------------------------------------------------------------------------


def _now():
    return timezone.now()


def ago(days, hours=0):
    return _now() - timedelta(days=days, hours=hours)


def day(offset):
    return timezone.localdate() + timedelta(days=offset)


def sc(catalog, code):
    return SystemCatalogItem.objects.filter(catalog=catalog, code=code).first()


def origen(code):
    """Origen items are client-configured (§13.1 pending); use whatever matches, if any."""
    return sc(SystemCatalog.ORIGEN, code)


# --- Reset ---------------------------------------------------------------------------------


def purge():
    """Deletes the demo client, its data, files and history, and its password-less people."""
    client = Client.objects.filter(slug=SLUG).first()
    if client is None:
        return False
    with transaction.atomic(), tenant_context(client):
        files = []
        for model in (
            Adjunto,
            Evidencia,
            Documento,
            apps.get_model("formularios", "Acta"),
            apps.get_model("aprendizaje", "Bloque"),
        ):
            files += [o.archivo.name for o in model.unscoped.filter(client=client) if o.archivo]
        for label in ("aprendizaje.BloqueItem", "aprendizaje.Encabezado"):
            files += [
                o.imagen.name
                for o in apps.get_model(label).unscoped.filter(client=client)
                if o.imagen
            ]
        order = [
            "bitacora.TicketAfectado", "bitacora.TicketComentario", "bitacora.TicketTransicion",
            "bitacora.Ticket", "aprendizaje.LeccionVista", "aprendizaje.Inscripcion",
            "aprendizaje.Ajustes", "aprendizaje.Encabezado", "aprendizaje.BloqueItem", "aprendizaje.Bloque",
            "aprendizaje.Leccion",
            "aprendizaje.Curso", "formularios.Evaluacion", "formularios.Acta", "formularios.Criterio",
            "formularios.ListaObservacion", "formularios.Respuesta", "formularios.Enlace",
            "formularios.Opcion", "formularios.Pregunta", "formularios.Cuestionario",
            "formularios.Carga", "formularios.Persona", "dashboard.Preferencia", "dashboard.ValorManual",
            "dashboard.IndicadorConfig", "guia.Documento", "ruta.Evidencia", "ruta.Actividad",
            "matriz.Foto", "matriz.Dependencia", "matriz.Adjunto", "matriz.Comentario",
            "matriz.Transicion", "matriz.Impacto", "catalogs.GrupoImpactado",
            "catalogs.UnidadOrganizacional", "catalogs.Cargo", "catalogs.CategoriaResponsable",
            "catalogs.Canal",
        ]  # fmt: skip
        Membership.objects.filter(client=client).delete()
        for label in order:
            apps.get_model(label).unscoped.filter(client=client).delete()
        for model in apps.get_models():  # history rows of this client's records
            if model.__name__.startswith("Historical") and "client" in [
                f.name for f in model._meta.fields
            ]:
                model._base_manager.filter(client_id=client.pk).delete()
        Invitation.objects.filter(client=client).delete()
        client.delete()
        User.objects.filter(email__iendswith=f"@{DOMAIN}").delete()
    for name in files:
        default_storage.delete(name)
    return True


# --- Build ---------------------------------------------------------------------------------


PEOPLE = [
    # key, first, last, role, cargo, departamento, grupos
    ("valentina", "Valentina", "Rojas", Role.EQUIPO_CAMBIO, "Consultora de cambio", "Personas y Cultura", []),
    ("matias", "Matías", "Fuentes", Role.EQUIPO_CAMBIO, "PMO", "Tecnología", ["Back office operaciones"]),
    ("camila", "Camila", "Soto", Role.CAPITAN, "Jefa de sucursal", "Operaciones", ["Cajeros de sucursal", "Jefes de sucursal"]),
    ("diego", "Diego", "Paredes", Role.CAPITAN, "Supervisor de contact center", "Comercial", ["Contact center"]),
    ("fernanda", "Fernanda", "Ibáñez", Role.GUIA, "Analista de operaciones", "Operaciones", ["Cajeros de sucursal", "Ejecutivos comerciales"]),
    ("joaquin", "Joaquín", "Herrera", Role.GUIA, "Analista de operaciones", "Operaciones", ["Back office operaciones", "Contact center"]),
    ("andres", "Andrés", "Molina", Role.EQUIPO_TECNICO, "Arquitecto TI", "Tecnología", []),
    ("paula", "Paula", "Navarro", Role.EQUIPO_TECNICO, "Analista de soporte", "Tecnología", ["Soporte TI"]),
    ("ricardo", "Ricardo", "Vidal", Role.PATROCINADOR, "Gerente de Operaciones", "Operaciones", []),
    ("lorena", "Lorena", "Castillo", Role.LIDER_AREA, "Jefa de sucursal", "Operaciones", []),
    ("tomas", "Tomás", "Aguirre", Role.LIDER_AREA, "Supervisor de contact center", "Comercial", []),
]  # fmt: skip

GRUPOS = [
    ("Cajeros de sucursal", 180, "Atienden caja en las 22 sucursales."),
    ("Ejecutivos comerciales", 95, "Abren cuentas y venden productos en sucursal."),
    ("Jefes de sucursal", 40, "Aprueban excepciones y cuadran la caja diaria."),
    ("Back office operaciones", 60, "Conciliación, transferencias y cierre diario."),
    ("Contact center", 75, "Atención telefónica y por chat."),
    ("Riesgo y cumplimiento", 25, "Prevención de fraude, auditoría y reportes al regulador."),
    ("Soporte TI", 30, "Mesa de ayuda y soporte a sucursales."),
]

UNIDADES = [
    (U.DEPARTAMENTO, "Operaciones"),
    (U.DEPARTAMENTO, "Comercial"),
    (U.DEPARTAMENTO, "Tecnología"),
    (U.DEPARTAMENTO, "Riesgo"),
    (U.DEPARTAMENTO, "Personas y Cultura"),
    (U.AREA, "Gerencia de Transformación"),
    (U.OFICINA, "Casa Matriz"),
    (U.SUCURSAL, "Sucursal Centro"),
    (U.SUCURSAL, "Sucursal Norte"),
    (U.SUCURSAL, "Sucursal Costa"),
]

CARGOS = [
    "Cajero/a", "Ejecutivo/a comercial", "Jefa de sucursal", "Analista de operaciones",
    "Agente de contact center", "Supervisor de contact center", "Gerente de Operaciones",
    "Arquitecto TI", "Analista de soporte", "Consultora de cambio", "PMO",
]  # fmt: skip

CATEGORIAS = ["Dueño de proceso", "Sponsor", "Experto técnico", "Líder de cambio"]
CANALES = [
    "Correo corporativo", "Intranet", "Reunión de equipo", "Video del gerente",
    "Afiches en sucursal", "WhatsApp de sucursal",
]  # fmt: skip


class Builder:
    def __init__(self, admin_email, out=print):
        self.admin_email = admin_email.strip().lower()
        self.out = out

    def run(self):
        admin = User.objects.filter(email__iexact=self.admin_email).first()
        if admin is None:
            raise ValueError(f"No existe una cuenta con el correo {self.admin_email}.")
        self.client = Client.objects.create(
            name=NAME, slug=SLUG, enabled_modules=list(Module.values), created_by=admin
        )
        with transaction.atomic(), tenant_context(self.client):
            self.catalogs()
            self.members(admin)
            self.matriz()
            self.ruta()
            self.bitacora()
            self.formularios()
            self.aprendizaje()
            self.dashboard()
            self.guia()
        return self.client

    # Catalogs and people ------------------------------------------------------------------

    def catalogs(self):
        self.grupo = {
            n: GrupoImpactado.objects.create(name=n, personas=p, description=d, order=i)
            for i, (n, p, d) in enumerate(GRUPOS)
        }
        self.unidad = {
            n: UnidadOrganizacional.objects.create(kind=k, name=n, order=i)
            for i, (k, n) in enumerate(UNIDADES)
        }
        self.cargo = {n: Cargo.objects.create(name=n, order=i) for i, n in enumerate(CARGOS)}
        self.categoria = {
            n: CategoriaResponsable.objects.create(name=n, order=i)
            for i, n in enumerate(CATEGORIAS)
        }
        self.canal = {n: Canal.objects.create(name=n, order=i) for i, n in enumerate(CANALES)}
        self.out(f"Catálogos: {len(GRUPOS)} grupos, {len(UNIDADES)} unidades, {len(CARGOS)} cargos")

    def members(self, admin):
        Membership.objects.update_or_create(
            user=admin,
            client=self.client,
            defaults={
                "role": Role.ADMINISTRACION,
                "is_active": True,
                "cargo": self.cargo["Consultora de cambio"],
                "departamento": self.unidad["Personas y Cultura"],
            },
        )
        self.admin = admin
        self.u = {"presentador": admin}  # so the presenter has their own items in «Para ti»
        for key, first, last, role, cargo, depto, grupos in PEOPLE:
            user = User.objects.create_user(  # no password: can't log in
                email=f"{key}.{last.lower().replace('á', 'a').replace('í', 'i')}@{DOMAIN}",
                first_name=first,
                last_name=last,
            )
            m = Membership.objects.create(
                user=user,
                client=self.client,
                role=role,
                cargo=self.cargo[cargo],
                departamento=self.unidad[depto],
            )
            m.grupos.set([self.grupo[g] for g in grupos])
            self.u[key] = user
        self.out(f"Personas: {len(PEOPLE)} miembros sin acceso + {admin.email} (Administración)")

    # Matriz -------------------------------------------------------------------------------

    def impacto(self, *, by, created, path=(), **fields):
        impacto = Impacto(registrado_por=by, **fields)
        impacto.save()
        steps = list(path)
        for target, reason in steps:
            workflow.transition(impacto, target, user=self.u["valentina"], reason=reason)
        Impacto.objects.filter(pk=impacto.pk).update(created_at=created)
        span = (_now() - created) / (len(steps) + 1)
        for i, t in enumerate(impacto.transiciones.order_by("pk"), start=1):
            Transicion.objects.filter(pk=t.pk).update(fecha=created + span * i)
        return impacto

    def matriz(self):
        T = SystemCatalog
        tipo = lambda c: sc(T.TIPO_IMPACTO, c)  # noqa: E731
        tiempo = lambda c: sc(T.TIEMPO, c)  # noqa: E731
        tcc = lambda c: sc(T.TIPO_CAMBIO_CONOCIMIENTO, c)  # noqa: E731
        ev = lambda c: sc(T.EVIDENCIA_CIERRE, c)  # noqa: E731
        g, u, cat = self.grupo, self.u, self.categoria
        EV, EA, AT, CE = "evaluado", "en_atencion", "atendido", "cerrado"
        base = dict(requiere_movilizacion=True, origen=origen("levantamiento_con_el_grupo"))

        self.imp = {}
        I = self.imp  # noqa: E741
        I["caja"] = self.impacto(
            titulo="Nuevo flujo de apertura y cuadre de caja",
            descripcion="La apertura, los arqueos y el cuadre de caja pasan del sistema antiguo y "
            "planillas Excel al módulo de caja de Núcleo.",
            situacion_actual="Cuadre manual en Excel; diferencias se investigan al día siguiente.",
            situacion_futura="Cuadre en línea en Núcleo; las diferencias se ven en el momento.",
            tipo=tipo("proceso"), tiempo=tiempo("travesia"), grupo=g["Cajeros de sucursal"],
            personas_impactadas=180, magnitud=4,
            riesgo_descripcion="Filas más largas y errores de cuadre las primeras semanas.",
            probabilidad=3, severidad=3, requiere_comunicacion=True, requiere_formacion=True,
            tipo_cambio_conocimiento=tcc("herramienta_proceso_nuevo"), formacion_criticidad="alta",
            formacion_momento=tiempo("travesia"),
            medida="Formación práctica en sala de simulación + acompañamiento en sucursal la "
            "primera semana.",
            responsable=u["camila"], responsable_categoria=cat["Dueño de proceso"],
            fecha_compromiso=day(35), criterio_evidencia=ev("formacion_completada"),
            criterio_meta=Decimal("90"), criterio_descripcion="90 % de cajeros certificados por "
            "su jefe antes del go-live", requiere_certificacion_lider=True,
            by=u["valentina"], created=ago(62), path=[(EV, ""), (EA, "")], **base,
        )  # fmt: skip
        I["ficha"] = self.impacto(
            titulo="Ficha única de cliente en el contact center",
            descripcion="Los agentes dejan de consultar tres sistemas: Núcleo muestra la ficha "
            "completa del cliente en una pantalla.",
            situacion_actual="Tres pantallas y copiar y pegar entre sistemas.",
            situacion_futura="Una ficha con productos, reclamos y contactos.",
            tipo=tipo("tecnologia"), tiempo=tiempo("travesia"), grupo=g["Contact center"],
            personas_impactadas=75, magnitud=3, riesgo_descripcion="Tiempo de atención sube "
            "mientras aprenden la ficha.", probabilidad=3, severidad=2,
            requiere_comunicacion=True, requiere_formacion=True,
            tipo_cambio_conocimiento=tcc("herramienta_proceso_nuevo"), formacion_criticidad="media",
            formacion_momento=tiempo("travesia"), medida="Curso e-learning + cuestionario.",
            responsable=u["diego"], responsable_categoria=cat["Dueño de proceso"],
            fecha_compromiso=day(20), criterio_evidencia=ev("verificacion_grupo"),
            criterio_meta=Decimal("80"), criterio_descripcion="80 % aprueba el cuestionario",
            by=u["valentina"], created=ago(55), path=[(EV, ""), (EA, "")], **base,
        )  # fmt: skip
        I["apertura"] = self.impacto(
            titulo="Apertura de cuentas 100 % digital en sucursal",
            descripcion="Los ejecutivos abren cuentas en tablet, con firma electrónica y sin "
            "papel.", situacion_actual="Formularios en papel y digitación posterior.",
            situacion_futura="Contrato digital firmado en tablet.",
            tipo=tipo("proceso"), tiempo=tiempo("cumbre"), grupo=g["Ejecutivos comerciales"],
            personas_impactadas=95, magnitud=3, riesgo_descripcion="Rechazo de clientes mayores "
            "a firmar en pantalla.", probabilidad=2, severidad=3, requiere_comunicacion=True,
            requiere_formacion=True, tipo_cambio_conocimiento=tcc("funcion_modificada"),
            formacion_criticidad="media", formacion_momento=tiempo("cumbre"),
            medida="Guion de explicación al cliente y formación en sucursal piloto.",
            responsable=u["fernanda"], responsable_categoria=cat["Dueño de proceso"],
            fecha_compromiso=day(60), criterio_evidencia=ev("adopcion_medida"),
            criterio_meta=Decimal("70"), criterio_descripcion="70 % de aperturas digitales en el "
            "primer mes", by=u["valentina"], created=ago(48), path=[(EV, "")], **base,
        )  # fmt: skip
        I["conciliacion"] = self.impacto(
            titulo="Conciliación automática en back office",
            descripcion="La conciliación diaria pasa a ser automática; el equipo revisa solo "
            "excepciones.", situacion_actual="Conciliación manual de 6 horas diarias.",
            situacion_futura="Revisión de excepciones en 1 hora.",
            tipo=tipo("rol_funcion"), tiempo=tiempo("cumbre"), grupo=g["Back office operaciones"],
            personas_impactadas=60, magnitud=4, riesgo_descripcion="Temor a perder el puesto; "
            "resistencia al cambio de rol.", probabilidad=3, severidad=4,
            requiere_comunicacion=True, requiere_formacion=True,
            tipo_cambio_conocimiento=tcc("funcion_nueva"), formacion_criticidad="alta",
            formacion_momento=tiempo("cumbre"),
            medida="Comunicación del gerente sobre el nuevo rol de analista + plan de "
            "reconversión.", responsable=u["matias"], responsable_categoria=cat["Sponsor"],
            fecha_compromiso=day(75), criterio_evidencia=ev("aprobacion_responsable"),
            criterio_meta=Decimal("100"), criterio_descripcion="Plan de reconversión aprobado "
            "por la gerencia", by=u["matias"], created=ago(40), path=[(EV, ""), (EA, "")],
            **base,
        )  # fmt: skip
        I["fraude"] = self.impacto(
            titulo="Nuevas alertas de fraude en tiempo real",
            descripcion="Riesgo y cumplimiento recibe alertas en línea en vez de un reporte "
            "diario.", tipo=tipo("tecnologia"), tiempo=tiempo("travesia"),
            grupo=g["Riesgo y cumplimiento"], personas_impactadas=25, magnitud=2,
            riesgo_descripcion="Exceso de alertas falsas los primeros días.", probabilidad=2,
            severidad=2, requiere_comunicacion=False, requiere_formacion=True,
            tipo_cambio_conocimiento=tcc("herramienta_proceso_nuevo"), formacion_criticidad="baja",
            formacion_momento=tiempo("travesia"), medida="Taller con el proveedor.",
            responsable=u["andres"], responsable_categoria=cat["Experto técnico"],
            fecha_compromiso=day(-10), criterio_evidencia=ev("tickets_bajo_umbral"),
            criterio_meta=Decimal("5"), criterio_descripcion="Menos de 5 tickets por semana",
            by=u["andres"], created=ago(50), path=[(EV, ""), (EA, ""), (AT, "")], **base,
        )  # fmt: skip
        I["horario"] = self.impacto(
            titulo="Cambio de horario de cierre de sucursales durante la migración",
            descripcion="El fin de semana de migración las sucursales cierran el viernes a las "
            "13:00.", tipo=tipo("proceso"), tiempo=tiempo("cumbre"),
            grupo=g["Jefes de sucursal"], personas_impactadas=40, magnitud=2,
            riesgo_descripcion="Reclamos de clientes que no se enteraron.", probabilidad=3,
            severidad=2, requiere_comunicacion=True, requiere_formacion=False,
            tipo_cambio_conocimiento=tcc("sin_aprendizaje"), medida="Campaña a clientes y "
            "afiches en sucursal 3 semanas antes.", responsable=u["ricardo"],
            responsable_categoria=cat["Sponsor"], fecha_compromiso=day(25),
            criterio_evidencia=ev("aprobacion_responsable"), criterio_descripcion="Campaña "
            "publicada y validada por el gerente", by=u["valentina"], created=ago(30),
            path=[(EV, "")], **base,
        )  # fmt: skip
        I["claves"] = self.impacto(
            titulo="Nuevas credenciales y doble factor para todo el personal",
            descripcion="Cada colaborador activa su usuario de Núcleo con doble factor.",
            tipo=tipo("tecnologia"), tiempo=tiempo("horizonte"), grupo=g["Soporte TI"],
            personas_impactadas=520, magnitud=1, riesgo_descripcion="Mesa de ayuda saturada el "
            "día de activación.", probabilidad=4, severidad=2, requiere_comunicacion=True,
            requiere_formacion=False, tipo_cambio_conocimiento=tcc("sin_aprendizaje"),
            medida="Activación escalonada por sucursal y guía paso a paso.",
            responsable=u["paula"], responsable_categoria=cat["Experto técnico"],
            fecha_compromiso=day(-25), criterio_evidencia=ev("tickets_bajo_umbral"),
            criterio_meta=Decimal("20"), criterio_descripcion="Menos de 20 tickets de acceso "
            "por día", by=u["paula"], created=ago(70),
            path=[(EV, ""), (EA, ""), (AT, ""), (CE, "")], **base,
        )  # fmt: skip
        I["reportes"] = self.impacto(
            titulo="Reportes regulatorios generados desde Núcleo",
            descripcion="Los reportes al regulador salen de Núcleo y no de planillas.",
            tipo=tipo("proceso"), tiempo=tiempo("legado"), grupo=g["Riesgo y cumplimiento"],
            personas_impactadas=25, magnitud=3, riesgo_descripcion="Multa si un reporte sale "
            "con errores.", probabilidad=2, severidad=4, requiere_comunicacion=True,
            requiere_formacion=True, tipo_cambio_conocimiento=tcc("funcion_modificada"),
            formacion_criticidad="alta", formacion_momento=tiempo("cumbre"),
            medida="Doble corrida (sistema antiguo y Núcleo) durante dos meses.",
            responsable=u["andres"], responsable_categoria=cat["Experto técnico"],
            fecha_compromiso=day(110), criterio_evidencia=ev("aprobacion_responsable"),
            criterio_descripcion="Dos meses de doble corrida sin diferencias",
            by=u["valentina"], created=ago(20), path=[(EV, "")], **base,
        )  # fmt: skip
        I["cultura"] = self.impacto(
            titulo="De «esto siempre se hizo así» a mejora continua",
            descripcion="Los equipos de sucursal proponen mejoras al nuevo proceso en vez de "
            "volver al anterior.", tipo=tipo("cultura"), tiempo=tiempo("legado"),
            grupo=g["Jefes de sucursal"], personas_impactadas=40, magnitud=3,
            riesgo_descripcion="Vuelta a planillas paralelas.", probabilidad=3, severidad=3,
            requiere_comunicacion=True, requiere_formacion=False,
            tipo_cambio_conocimiento=tcc("sin_aprendizaje"), medida="Reconocimiento mensual a "
            "sucursales con mejoras implementadas.", responsable=u["ricardo"],
            responsable_categoria=cat["Líder de cambio"], fecha_compromiso=day(150),
            criterio_evidencia=ev("adopcion_medida"), criterio_meta=Decimal("10"),
            criterio_descripcion="10 mejoras propuestas por sucursales",
            by=u["valentina"], created=ago(15), path=[], **base,
        )  # fmt: skip
        I["descartado"] = self.impacto(
            titulo="Cambio de uniforme de cajeros",
            descripcion="Se evaluó cambiar el uniforme junto con el nuevo sistema.",
            tipo=tipo("cultura"), tiempo=tiempo("cumbre"), grupo=g["Cajeros de sucursal"],
            personas_impactadas=180, by=u["camila"], created=ago(45),
            path=[("descartado", "No tiene relación con el proyecto Núcleo; se deriva a "
                   "Personas y Cultura.")],
        )  # fmt: skip
        I["firmas"] = self.impacto(
            titulo="Validación de firmas en pagos de cheques",
            descripcion="La validación de firma pasa a hacerse con imagen digital en Núcleo.",
            tipo=tipo("proceso"), tiempo=tiempo("travesia"), grupo=g["Cajeros de sucursal"],
            personas_impactadas=180, magnitud=2, riesgo_descripcion="Pagos rechazados por "
            "imágenes de baja calidad.", probabilidad=3, severidad=3,
            requiere_comunicacion=True, requiere_formacion=True,
            tipo_cambio_conocimiento=tcc("funcion_modificada"), formacion_criticidad="media",
            formacion_momento=tiempo("travesia"), medida="Re-digitalización de firmas antiguas.",
            responsable=u["camila"], responsable_categoria=cat["Dueño de proceso"],
            fecha_compromiso=day(10), criterio_evidencia=ev("tickets_bajo_umbral"),
            criterio_meta=Decimal("3"), criterio_descripcion="Menos de 3 rechazos por sucursal "
            "a la semana", by=u["camila"], created=ago(58),
            path=[(EV, ""), (EA, ""), (AT, ""), ("reabierto", "Siguen los rechazos en Sucursal "
                  "Norte: imágenes de firmas antiguas.")],
            **base,
        )  # fmt: skip
        # Proposals from the field, waiting for the change team.
        I["cobranza"] = self.impacto(
            titulo="Cobranza telefónica sin acceso al nuevo historial de pagos",
            descripcion="Los agentes de cobranza no ven los pagos hechos en sucursal el mismo día.",
            situacion_actual="Ven los pagos al día siguiente.", tipo=tipo("tecnologia"),
            tiempo=tiempo("travesia"), grupo_sugerido="Cobranza", personas_impactadas=18,
            origen=origen("levantamiento_con_el_grupo"), by=u["diego"], created=ago(3),
        )  # fmt: skip
        I["chat"] = self.impacto(
            titulo="Chat con clientes durante el fin de semana de migración",
            descripcion="El contact center necesita un guion para explicar por qué no se ven los "
            "movimientos durante la migración.", tipo=tipo("conocimiento"),
            tiempo=tiempo("cumbre"), grupo=g["Contact center"], personas_impactadas=75,
            by=u["joaquin"], created=ago(2), origen=origen("levantamiento_con_el_grupo"),
        )  # fmt: skip

        # Priority adjusted by the change team, with its justification.
        f = I["horario"]
        f.prioridad_ajustada, f.prioridad_justificacion = (
            1,
            (
                "Toca a todos los clientes de sucursal: el comité lo sube a P1 por riesgo reputacional."
            ),
        )
        f.save()
        # Dependencies: the cashiers' training waits for the new till process.
        Dependencia.objects.create(
            impacto=I["firmas"], depende_de=I["caja"], creada_por=u["valentina"]
        )
        Dependencia.objects.create(
            impacto=I["apertura"], depende_de=I["ficha"], creada_por=u["matias"]
        )
        Dependencia.objects.create(
            impacto=I["reportes"], depende_de=I["conciliacion"], creada_por=u["matias"]
        )
        # Conversation and links.
        for key, who, text, days in [
            ("caja", "camila", "En Sucursal Centro ya probamos la sala de simulación: muy bien recibida.", 12),
            ("caja", "valentina", "Agendado el acompañamiento de la primera semana con los guías.", 9),
            ("conciliacion", "ricardo", "El directorio pidió ver el plan de reconversión antes de fin de mes.", 6),
            ("conciliacion", "matias", "Borrador listo; lo revisamos el jueves con Personas y Cultura.", 4),
            ("firmas", "camila", "Sucursal Norte reporta 9 rechazos esta semana.", 2),
            ("horario", "ricardo", "Aprobado el texto de la campaña.", 5),
        ]:  # fmt: skip
            c = Comentario.objects.create(impacto=I[key], autor=u[who], texto=text)
            Comentario.objects.filter(pk=c.pk).update(fecha=ago(days))
        for key, name, url in [
            ("caja", "Manual de caja Núcleo v2", "https://example.com/nucleo/manual-caja"),
            ("conciliacion", "Plan de reconversión (borrador)", "https://example.com/nucleo/reconversion"),
            ("horario", "Afiche para sucursales", "https://example.com/nucleo/afiche-horario"),
        ]:  # fmt: skip
            Adjunto.objects.create(impacto=I[key], nombre=name, url=url, subido_por=u["valentina"])
        # Snapshot at the close of the first stage.
        foto = Foto.objects.create(
            tiempo=sc(SystemCatalog.TIEMPO, "horizonte"),
            nota="Cierre de Horizonte: comité de avance",
            datos=export.impacto_rows(
                Impacto.objects.select_related("grupo", "tipo", "tiempo", "responsable")
                .prefetch_related("dependencias__depende_de")
                .filter(numero__lte=9)
            ),
            creada_por=u["valentina"],
        )
        Foto.objects.filter(pk=foto.pk).update(fecha=ago(28))
        self.out(f"Matriz: {Impacto.objects.count()} impactos en todos los estados")

    # Ruta ---------------------------------------------------------------------------------

    def ruta(self):
        F = lambda c: sc(SystemCatalog.FRENTE, c)  # noqa: E731
        T = lambda c: sc(SystemCatalog.TIEMPO, c)  # noqa: E731
        g, u, I, ch = self.grupo, self.u, self.imp, self.canal  # noqa: E741
        DONE, VER, CUR, NO = "completado", "verificado", "en_curso", "no_iniciado"
        rows = [
            # titulo, frente, tiempo, grupos, impactos, responsable, plan, real, estado, canal, vocero, extra
            ("Lanzamiento del proyecto Núcleo", "comunicacion", "horizonte", list(g.values()), [], "ricardo", -70, -70, VER, "Video del gerente", "Ricardo Vidal", {}),
            ("Diagnóstico de preparación por grupo", "impactos", "horizonte", list(g.values()), [], "valentina", -60, -58, VER, None, "", {}),
            ("Red de guías: formación inicial", "movilizacion", "horizonte", [g["Cajeros de sucursal"], g["Back office operaciones"]], [], "valentina", -50, -45, DONE, None, "", {}),
            ("Activación de credenciales por sucursal", "formacion", "horizonte", [g["Soporte TI"]], [I["claves"]], "paula", -40, -38, VER, "Intranet", "", {}),
            ("Simulación de caja en Sucursal Centro", "formacion", "travesia", [g["Cajeros de sucursal"]], [I["caja"]], "camila", -14, -12, DONE, None, "", {}),
            ("Curso e-learning ficha única", "formacion", "travesia", [g["Contact center"]], [I["ficha"]], "diego", -10, None, CUR, None, "", {}),
            ("Comunicado: qué cambia en tu caja", "comunicacion", "travesia", [g["Cajeros de sucursal"], g["Jefes de sucursal"]], [I["caja"]], "valentina", -20, -20, DONE, "Correo corporativo", "Ricardo Vidal", {}),
            ("Reunión de jefes de sucursal: nuevo rol", "movilizacion", "travesia", [g["Jefes de sucursal"]], [I["caja"], I["cultura"]], "camila", -8, None, NO, "Reunión de equipo", "Camila Soto", {}),
            ("Taller de alertas de fraude con el proveedor", "formacion", "travesia", [g["Riesgo y cumplimiento"]], [I["fraude"]], "andres", -30, -26, DONE, None, "", {}),
            ("Conversatorio sobre el nuevo rol de back office", "movilizacion", "cumbre", [g["Back office operaciones"]], [I["conciliacion"]], "matias", 6, None, NO, "Reunión de equipo", "Ricardo Vidal", {}),
            ("Campaña de horario especial a clientes", "comunicacion", "cumbre", [g["Jefes de sucursal"]], [I["horario"]], "ricardo", 4, None, CUR, "Afiches en sucursal", "", {}),
            ("Formación en apertura digital (piloto)", "formacion", "cumbre", [g["Ejecutivos comerciales"]], [I["apertura"]], "fernanda", 15, None, NO, None, "", {}),
            ("Guion para el chat del fin de semana", "comunicacion", "cumbre", [g["Contact center"]], [], "joaquin", 10, None, NO, "WhatsApp de sucursal", "", {}),
            ("Plan de doble corrida de reportes", "impactos", "legado", [g["Riesgo y cumplimiento"]], [I["reportes"]], "andres", 40, None, NO, None, "", {}),
            ("Visita del gerente a Sucursal Norte", "movilizacion", "travesia", [g["Cajeros de sucursal"]], [I["firmas"]], "ricardo", None, -3, DONE, "Reunión de equipo", "Ricardo Vidal", {"no_planificada": True}),
            ("Boletín mensual de avance", "comunicacion", "travesia", list(g.values()), [], "valentina", -5, -2, DONE, "Intranet", "Valentina Rojas", {}),
            ("Preparar el comité de avance con el patrocinador", "impactos", "travesia", [], [I["conciliacion"], I["horario"]], "presentador", 2, None, CUR, None, "", {}),
        ]  # fmt: skip
        for i, (
            titulo,
            frente,
            tiempo,
            grupos,
            imps,
            who,
            plan,
            real,
            estado,
            canal,
            vocero,
            extra,
        ) in enumerate(rows):
            a = Actividad.objects.create(
                titulo=titulo, frente=F(frente), tiempo=T(tiempo), responsable=u[who],
                fecha_planificada=day(plan) if plan is not None else None,
                fecha_real=day(real) if real is not None else None, estado=estado,
                canal=ch.get(canal) if canal else None, vocero=vocero,
                evidencia="Lista de asistencia y fotos" if estado in (DONE, VER) else "",
                indicador="% del grupo alcanzado" if frente != "impactos" else "",
                registrado_por=u["valentina"], **extra,
            )  # fmt: skip
            a.grupos.set(grupos)
            a.impactos.set(imps)
            Actividad.objects.filter(pk=a.pk).update(created_at=ago(80 - i * 4))
        Evidencia.objects.create(
            actividad=Actividad.objects.get(titulo__startswith="Simulación de caja"),
            nombre="Fotos de la simulación",
            url="https://example.com/nucleo/fotos-simulacion",
            subido_por=u["camila"],
        )
        self.out(f"Ruta: {len(rows)} actividades en los cuatro frentes")

    # Bitácora -----------------------------------------------------------------------------

    ACTIONS = frozenset({Action.CLASSIFY, Action.REGISTER, Action.EDIT_DERIVED})

    def ticket(self, titulo, descripcion, categoria, *, by, grupo, days, steps=(), **extra):
        t = Ticket.objects.create(
            titulo=titulo, descripcion=descripcion,
            categoria=sc(SystemCatalog.CATEGORIA_TICKET, categoria), grupo=self.grupo.get(grupo),
            registrado_por=self.u[by], **extra,
        )  # fmt: skip
        created = ago(days)
        marks = {"created_at": created}
        for target, who, hours, reason in steps:
            if target == "validar":
                ticket_flow.validate(t, user=self.u[who], actions=self.ACTIONS)
                continue
            ticket_flow.transition(t, target, user=self.u[who], actions=self.ACTIONS, reason=reason)
            at = created + timedelta(hours=hours)
            last = t.transiciones.order_by("-pk").first()
            TicketTransicion.objects.filter(pk=last.pk).update(fecha=at)
            marks.setdefault("primera_respuesta_at", at)
            if target == "resuelto":
                marks["resuelto_at"] = at
            if target == "cerrado":
                marks["cerrado_at"] = at
        Ticket.objects.filter(pk=t.pk).update(**marks)
        t.refresh_from_db()
        return t

    def bitacora(self):
        C, V, R, X, TI = "en_clasificacion", "validado", "resuelto", "cerrado", "derivado_ti"
        k = self.ticket
        tk = {}
        tk["cuadre"] = k("No cuadra la caja al cierre en Núcleo", "Diferencia de $12.000 que no aparece en el detalle.", "tecnico", by="camila", grupo="Cajeros de sucursal", days=12, steps=[(C, "fernanda", 1, ""), (V, "fernanda", 2, ""), (TI, "fernanda", 3, ""), (R, "paula", 20, ""), (X, "fernanda", 26, "")])  # fmt: skip
        tk["arqueo"] = k("¿Cómo registro un arqueo sorpresa?", "No encuentro la opción en el menú de caja.", "conocimiento", by="camila", grupo="Cajeros de sucursal", days=11, steps=[(C, "fernanda", 2, ""), (V, "fernanda", 3, ""), (R, "fernanda", 5, ""), (X, "fernanda", 8, "")])  # fmt: skip
        k("Otra vez: arqueo sorpresa", "Una cajera nueva tampoco encuentra el arqueo.", "conocimiento", by="fernanda", grupo="Cajeros de sucursal", days=6, recurrente_de=tk["arqueo"], steps=[(C, "fernanda", 1, ""), (V, "fernanda", 1, ""), (R, "fernanda", 4, ""), (X, "fernanda", 6, "")])  # fmt: skip
        k("Recurrente: arqueo sorpresa en Sucursal Costa", "Mismo caso, otra sucursal.", "conocimiento", by="fernanda", grupo="Cajeros de sucursal", days=2, recurrente_de=tk["arqueo"], steps=[(C, "fernanda", 1, ""), (V, "fernanda", 2, "")])  # fmt: skip
        tk["caida"] = k("Núcleo no responde en Sucursal Norte", "Ninguna caja puede operar desde las 10:15.", "tecnico", by="camila", grupo="Cajeros de sucursal", days=4, urgencia="grave", caso_cliente="INC-48211", steps=[(TI, "camila", 0.2, ""), ("validar", "fernanda", 0, ""), (R, "paula", 1.5, ""), (X, "fernanda", 3, "")])  # fmt: skip
        k("Ficha única carga lento en horario punta", "Entre 11 y 13 h la ficha demora 20 segundos.", "tecnico", by="diego", grupo="Contact center", days=3, steps=[(C, "joaquin", 1, ""), (V, "joaquin", 2, ""), (TI, "joaquin", 2, "")])  # fmt: skip
        k("Agentes vuelven a usar el sistema antiguo", "Algunos abren el sistema anterior «por si acaso».", "adopcion", by="diego", grupo="Contact center", days=5, steps=[(C, "joaquin", 3, ""), (V, "joaquin", 4, "")])  # fmt: skip
        k("Clientes mayores no quieren firmar en tablet", "En piloto 3 de 10 clientes pidieron papel.", "proceso", by="fernanda", grupo="Ejecutivos comerciales", days=7, steps=[(C, "fernanda", 2, ""), (V, "fernanda", 3, ""), (R, "fernanda", 30, "")])  # fmt: skip
        k("No llegó el comunicado del cambio de caja", "Sucursal Costa no recibió el correo.", "comunicacion", by="camila", grupo="Jefes de sucursal", days=9, steps=[(C, "fernanda", 1, ""), (V, "fernanda", 1, ""), (R, "fernanda", 2, ""), (X, "fernanda", 4, "")])  # fmt: skip
        k("Conciliación marca excepciones que no lo son", "Transferencias del mismo día aparecen como pendientes.", "tecnico", by="joaquin", grupo="Back office operaciones", days=1, steps=[(C, "joaquin", 0.5, "")])  # fmt: skip
        tk["cobranza"] = k("Cobranza no ve pagos hechos en sucursal", "Llamamos a clientes que ya pagaron.", "impacto_no_anticipado", by="diego", grupo="Contact center", days=3)  # fmt: skip
        k("Atajo de teclado para buscar cliente", "Propuesta: F2 para abrir la búsqueda.", "sugerencia_mejora", by="diego", grupo="Contact center", days=6)  # fmt: skip
        k("Error al imprimir comprobante de depósito", "La impresora de caja corta el comprobante.", "tecnico", by="camila", grupo="Cajeros de sucursal", days=0, urgencia="normal")  # fmt: skip
        k("Duda sobre límites de transferencia", "¿Cambian los límites diarios con Núcleo?", "conocimiento", by="joaquin", grupo="Back office operaciones", days=1)  # fmt: skip
        TI_RETURN = k("No puedo aprobar excepción de caja", "El botón de aprobar aparece deshabilitado.", "tecnico", by="camila", grupo="Jefes de sucursal", days=8, steps=[(C, "fernanda", 1, ""), (V, "fernanda", 2, ""), (TI, "fernanda", 2, ""), (C, "paula", 6, "No es falla: falta asignar el perfil de jefe. Lo resuelve Personas."), (V, "fernanda", 7, "")])  # fmt: skip
        TicketComentario.objects.create(
            ticket=TI_RETURN, autor=self.u["camila"], texto="Gracias, ya me asignaron el perfil."
        )
        for who in ("fernanda", "joaquin"):
            TicketAfectado.objects.create(ticket=tk["cuadre"], usuario=self.u[who])
        TicketAfectado.objects.create(ticket=tk["caida"], usuario=self.u["fernanda"])
        TicketComentario.objects.create(
            ticket=tk["caida"],
            autor=self.u["paula"],
            texto="Restablecido: era el enlace de comunicaciones de la sucursal.",
        )
        # The unanticipated impact went into the matrix (as the Bitácora does it).
        imp = self.imp["cobranza"]
        Ticket.objects.filter(pk=tk["cobranza"].pk).update(impacto=imp)
        Impacto.objects.filter(pk=imp.pk).update(origen=origen("bitacora") or imp.origen)
        self.out(f"Bitácora: {Ticket.objects.count()} tickets")

    # Formularios --------------------------------------------------------------------------

    FIRST = ["Ana", "Benjamín", "Carla", "Daniel", "Elisa", "Felipe", "Gabriela", "Hernán", "Isidora", "Javier", "Karina", "Luis", "Macarena", "Nicolás", "Olivia", "Pablo", "Renata", "Sebastián", "Trinidad", "Vicente"]  # fmt: skip
    LAST = ["Araya", "Bravo", "Cárcamo", "Díaz", "Espinoza", "Figueroa", "González", "Henríquez", "Jara", "Lagos", "Muñoz", "Núñez", "Orellana", "Pizarro", "Quiroz", "Reyes", "Salinas", "Tapia", "Urrutia", "Valdés"]  # fmt: skip

    def personas(self):
        rows = [
            # grupo, n, cargo, sucursal, departamento, supervisor key
            ("Cajeros de sucursal", 14, "Cajero/a", "Sucursal Centro", "Operaciones", "lorena"),
            (
                "Jefes de sucursal",
                6,
                "Jefa de sucursal",
                "Sucursal Norte",
                "Operaciones",
                "ricardo",
            ),
            ("Contact center", 12, "Agente de contact center", "Casa Matriz", "Comercial", "tomas"),
            (
                "Ejecutivos comerciales",
                8,
                "Ejecutivo/a comercial",
                "Sucursal Costa",
                "Comercial",
                "camila",
            ),
            (
                "Back office operaciones",
                7,
                "Analista de operaciones",
                "Casa Matriz",
                "Operaciones",
                "matias",
            ),
        ]
        out, i = {}, 0
        for grupo, n, cargo, sucursal, depto, sup in rows:
            out[grupo] = []
            for _ in range(n):
                first, last = self.FIRST[i % 20], self.LAST[(i * 7) % 20]
                out[grupo].append(
                    Persona.objects.create(
                        email=f"{first.lower()}.{last.lower()}{i}@{DOMAIN}".translate(
                            str.maketrans("áéíóúñ", "aeioun")
                        ),
                        nombre=first,
                        apellido=last,
                        cargo=cargo,
                        sucursal=sucursal,
                        oficina="Casa Matriz" if sucursal == "Casa Matriz" else "",
                        departamento=depto,
                        supervisor=self.u[sup].email,
                        grupo=self.grupo[grupo],
                    )  # fmt: skip
                )
                i += 1
        return out

    def cuestionario(self, titulo, impacto, preguntas, *, estado, by, days):
        c = Cuestionario.objects.create(
            titulo=titulo, impacto=impacto, nota_minima=Decimal("80"), intentos=2,
            vence=day(30), creado_por=self.u[by],
            instrucciones="Responde según lo aprendido en la formación. Tus respuestas son "
            "confidenciales, no anónimas.",
        )  # fmt: skip
        puntos = scoring.equal_split(len(preguntas))
        for i, (texto, tipo, opciones) in enumerate(preguntas):
            p = Pregunta.objects.create(
                cuestionario=c, orden=i, texto=texto, tipo=tipo, puntos=puntos[i]
            )
            for j, (o, ok) in enumerate(opciones):
                Opcion.objects.create(pregunta=p, orden=j, texto=o, correcta=ok)
        if estado != EstadoCuestionario.BORRADOR:
            assert not scoring.publish_errors(c), scoring.publish_errors(c)
            c.estado, c.publicado_at = estado, ago(days)
            c.save()
        return c

    def responder(self, c, personas, wrong_counts, days):
        """wrong_counts[i]: how many questions person i gets wrong (None = no answer)."""
        preguntas = list(c.preguntas.prefetch_related("opciones"))
        for n, (persona, wrong) in enumerate(zip(personas, wrong_counts, strict=False)):
            e = Enlace.objects.create(cuestionario=c, persona=persona)
            if wrong is None:
                continue
            elecciones = {}
            for q, p in enumerate(preguntas):
                ops = list(p.opciones.all())
                good = {o.pk for o in ops if o.correcta}
                bad = [o.pk for o in ops if not o.correcta]
                elecciones[p.pk] = {bad[0]} if q < wrong and bad else good
            per_q, total, passed = scoring.grade(c, elecciones)
            r = Respuesta.objects.create(
                enlace=e, intento=1, elecciones={str(k): sorted(v) for k, v in elecciones.items()},
                puntos_por_pregunta={str(k): str(v) for k, v in per_q.items()}, puntaje=total,
                aprobado=passed,
            )  # fmt: skip
            Respuesta.objects.filter(pk=r.pk).update(enviada_at=ago(days - n * 0.2))

    def formularios(self):
        S, M, YN = TipoPregunta.SIMPLE, TipoPregunta.MULTIPLE, TipoPregunta.SI_NO
        gente = self.personas()
        caja = self.cuestionario(
            "Operación de caja en Núcleo", self.imp["caja"],
            [
                ("¿Dónde se registra un arqueo sorpresa?", S, [("Caja → Arqueos", True), ("Reportes → Cierre", False), ("No se registra", False)]),
                ("¿Quién aprueba una diferencia de caja mayor a $50.000?", S, [("El jefe de sucursal", True), ("El cajero", False), ("Back office", False)]),
                ("¿Se puede cuadrar la caja sin conexión?", YN, [("Sí", False), ("No", True)]),
                ("¿Qué documentos acompañan un cuadre con diferencia? (marca todos)", M, [("Detalle de movimientos", True), ("Firma del jefe", True), ("Foto del cajero", False)]),
                ("¿Cuándo se ven las diferencias en Núcleo?", S, [("En el momento", True), ("Al día siguiente", False)]),
            ],
            estado=EstadoCuestionario.PUBLICADO, by="valentina", days=10,
        )  # fmt: skip
        self.caja = caja
        cajeros = gente["Cajeros de sucursal"] + gente["Jefes de sucursal"]
        # 14 cashiers: 11 pass, 2 fail, 1 pending; 6 branch heads: 5 pass, 1 pending.
        self.responder(
            caja,
            cajeros,
            [0, 0, 1, 0, 1, 0, 0, 2, 0, 1, 0, 3, 0, None, 0, 1, 0, 0, 0, None],
            days=9,
        )
        ficha = self.cuestionario(
            "Atención de clientes con la ficha única", self.imp["ficha"],
            [
                ("¿Dónde ves los reclamos abiertos del cliente?", S, [("En la ficha, pestaña Reclamos", True), ("En el correo", False)]),
                ("¿Qué debes verificar antes de dar un saldo por teléfono? (marca todos)", M, [("Identidad del cliente", True), ("Clave dinámica", True), ("Dirección de correo", False)]),
                ("¿La ficha muestra productos de otras empresas del grupo?", YN, [("Sí", True), ("No", False)]),
                ("Si la ficha no carga, ¿qué haces primero?", S, [("Registrar ticket en la Bitácora", True), ("Usar el sistema antiguo", False)]),
            ],
            estado=EstadoCuestionario.CERRADO, by="joaquin", days=16,
        )  # fmt: skip
        self.responder(
            ficha, gente["Contact center"], [0, 1, 0, 0, 2, 0, 1, 0, 0, 2, None, 0], days=15
        )
        self.cuestionario(
            "Conciliación por excepciones", self.imp["conciliacion"],
            [
                ("¿Qué es una excepción de conciliación?", S, [("Un movimiento que no calza automáticamente", True), ("Cualquier transferencia", False)]),
                ("¿Quién revisa las excepciones?", S, [("El analista de back office", True), ("El cajero", False)]),
            ],
            estado=EstadoCuestionario.BORRADOR, by="valentina", days=0,
        )  # fmt: skip

        # Leader's practical evaluation of the cashiers (after the questionnaire).
        lista = ListaObservacion.objects.create(
            impacto=self.imp["caja"], titulo="Observación práctica: cuadre de caja en Núcleo",
            instrucciones="Observa a cada cajero durante un cierre completo.",
            estado=EstadoLista.PUBLICADA, creada_por=self.u["valentina"],
        )  # fmt: skip
        for i, texto in enumerate(
            [
                "Abre la caja en Núcleo sin ayuda",
                "Registra un arqueo sorpresa correctamente",
                "Cuadra al cierre y explica cualquier diferencia",
                "Escala al jefe las diferencias sobre el límite",
            ]
        ):
            Criterio.objects.create(lista=lista, orden=i, texto=texto)
        lorena = self.u["lorena"]
        ids = list(lista.criterios.values_list("pk", flat=True))
        evaluaciones = certificacion.evaluations_for(lista, lorena)
        for n, ev in enumerate(evaluaciones[:-2]):  # the last two are still pending
            fails = n in (2, 6)
            resultados = {cid: not (fails and j == 2) for j, cid in enumerate(ids)}
            certificacion.save_results(
                ev, resultados, "Necesita repasar el cuadre con diferencias." if fails else "", ids
            )
        form = ActaForm(data={}, files={"archivo": SimpleUploadedFile("resumen-firmado-lorena.pdf", self.pdf(), "application/pdf")})  # fmt: skip
        assert form.is_valid(), form.errors
        certificacion.register_signed_summary(lista, lorena, form)
        self.out(
            f"Formularios: {Persona.objects.count()} personas, 3 cuestionarios, "
            f"{Respuesta.objects.count()} respuestas, 1 lista de observación"
        )

    @staticmethod
    def pdf():
        from weasyprint import HTML

        return HTML(
            string="<h1>Resumen firmado (demo)</h1><p>Observación práctica: cuadre de caja.</p>"
            "<p>Firma: Lorena Castillo</p>"
        ).write_pdf()

    # Ascenso y Aprendizaje ----------------------------------------------------------------

    @staticmethod
    def banner():
        """The bank's 1920 × 320 banner over the course pages, drawn here."""
        from io import BytesIO

        from PIL import Image, ImageDraw, ImageFont

        def font(size):
            try:  # in the Docker image (fonts-dejavu-core); the built-in one lacks accents
                return ImageFont.truetype("DejaVuSans.ttf", size)
            except OSError:
                return ImageFont.load_default(size=size)

        w, h = Encabezado.ANCHO, Encabezado.ALTO
        img = Image.new("RGB", (w, h))
        draw = ImageDraw.Draw(img)
        for y in range(h):  # dawn sky
            t = y / h
            draw.line([(0, y), (w, y)], fill=(int(28 + 40 * t), int(56 + 60 * t), int(92 + 70 * t)))
        draw.polygon(
            [(980, h), (1380, 70), (1560, 190), (1700, 110), (1920, 260), (1920, h)],
            fill=(64, 98, 132),
        )
        draw.polygon([(1180, h), (1500, 120), (1920, h)], fill=(42, 70, 100))
        draw.polygon(
            [(1500, 120), (1452, 170), (1478, 162), (1500, 178), (1524, 160), (1548, 170)],
            fill=(255, 255, 255),
        )
        draw.ellipse([(140, 96), (268, 224)], outline=(232, 176, 74), width=10)  # the bank's sun
        draw.text((320, 92), "Banco Altiplano", font=font(84), fill=(255, 255, 255))
        draw.text(
            (326, 202),
            "Escuela Núcleo · aprender para el cambio",
            font=font(38),
            fill=(189, 221, 252),
        )
        out = BytesIO()
        img.save(out, "PNG")
        return SimpleUploadedFile("banner-altiplano.png", out.getvalue(), "image/png")

    def curso(self, titulo, descripcion, lecciones, *, impactos_, **fields):
        """lecciones: (titulo, minutos, obligatoria, depende_de indexes, blocks), and each
        block is (tipo, titulo, texto, items[, grupos]) with items as (titulo, texto,
        correcta[, grupo])."""
        c = Curso.objects.create(titulo=titulo, descripcion=descripcion, **fields)
        c.impactos.set(impactos_)
        creadas = []
        for orden, (lt, minutos, obligatoria, deps, bloques) in enumerate(lecciones, start=1):
            leccion = Leccion.objects.create(
                curso=c, orden=orden, titulo=lt, minutos=minutos, obligatoria=obligatoria
            )
            leccion.depende_de.set([creadas[d] for d in deps])
            creadas.append(leccion)
            for bo, (tipo, bt, texto, items, *grupos) in enumerate(bloques, start=1):
                b = Bloque.objects.create(
                    leccion=leccion, orden=bo, tipo=tipo, titulo=bt, texto=texto,
                    grupos=grupos[0] if grupos else [],
                )  # fmt: skip
                for io, (it, ix, ok, *grupo) in enumerate(items, start=1):
                    BloqueItem.objects.create(
                        bloque=b, orden=io, titulo=it, texto=ix, correcta=ok,
                        grupo=grupo[0] if grupo else None,
                    )  # fmt: skip
        return c

    @staticmethod
    def pantalla(titulo, filas, marcada=None, nombre="pantalla.png"):
        """A simple drawing of a Núcleo screen, for the image blocks of the demo lesson."""
        from io import BytesIO

        from PIL import Image, ImageDraw, ImageFont

        def font(size):
            try:
                return ImageFont.truetype("DejaVuSans.ttf", size)
            except OSError:
                return ImageFont.load_default(size=size)

        img = Image.new("RGB", (1200, 675), (240, 240, 240))
        d = ImageDraw.Draw(img)
        d.rectangle([(0, 0), (1200, 70)], fill=(56, 73, 89))
        d.text((32, 18), "Núcleo · " + titulo, font=font(30), fill=(255, 255, 255))
        d.rectangle([(0, 70), (240, 675)], fill=(228, 239, 251))
        for n, menu in enumerate(["Cliente", "Productos", "Reclamos", "Caja", "Reportes"]):
            d.text((28, 110 + n * 56), menu, font=font(24), fill=(56, 73, 89))
        for n, (etiqueta, valor) in enumerate(filas):
            y = 110 + n * 92
            borde = (200, 118, 58) if n == marcada else (213, 219, 225)
            d.rounded_rectangle(
                [(280, y), (1160, y + 72)],
                radius=12,
                fill=(255, 255, 255),
                outline=borde,
                width=5 if n == marcada else 2,
            )
            d.text((308, y + 10), etiqueta, font=font(20), fill=(86, 97, 109))
            d.text((308, y + 36), valor, font=font(26), fill=(31, 41, 51))
        out = BytesIO()
        img.save(out, "PNG")
        return SimpleUploadedFile(nombre, out.getvalue(), "image/png")

    def muestrario(self, leccion):
        """One lesson that uses every block type, so the team sees what each one does."""
        fila = [
            ("Cliente", "María José Herrera · cédula 8-765-4321"),
            ("Productos", "Cuenta corriente · Tarjeta Oro · Crédito hipotecario"),
            ("Reclamos abiertos", "1 · Cobro duplicado (hace 3 días)"),
            ("Clave dinámica", "Validada hoy 10:42"),
        ]
        bloques = [
            (
                "texto",
                "Una sola pantalla",
                "Antes, para atender una llamada abríamos tres sistemas: cuentas, tarjetas y reclamos. Con Núcleo, la ficha única del cliente reúne todo en una pantalla.\n\nEn esta lección vas a ver qué tiene la ficha, cómo buscarla y qué revisar antes de dar información por teléfono.",
                {},
            ),
            (
                "nota",
                "Recuerda",
                "Nunca des un saldo sin validar la clave dinámica, aunque reconozcas la voz del cliente.",
                {},
            ),
            (
                "imagen",
                "Así se ve la ficha",
                "La ficha de una clienta de prueba: datos, productos, reclamos y validación.",
                {"archivo": self.pantalla("Ficha del cliente", fila, nombre="ficha-unica.png")},
            ),
            (
                "video",
                "Recorrido en video",
                "El equipo de formación grabó un recorrido de 4 minutos. Mientras se sube a YouTube, el enlace lleva a la intranet.",
                {"url": "https://example.com/nucleo/videos/ficha-unica"},
            ),
            (
                "documento",
                "Guía rápida para imprimir",
                "Una página con los atajos de la ficha, para tener junto al teclado.",
                {
                    "archivo": SimpleUploadedFile(
                        "guia-rapida-ficha.pdf", self.pdf(), "application/pdf"
                    )
                },
            ),
        ]
        orden = 0
        for tipo, titulo, texto, extra in bloques:
            orden += 1
            Bloque.objects.create(
                leccion=leccion, orden=orden, tipo=tipo, titulo=titulo, texto=texto, **extra
            )
        pasos = Bloque.objects.create(
            leccion=leccion,
            orden=orden + 1,
            tipo="pasos",
            titulo="Buscar una ficha en tres pasos",
            texto="Desde cualquier pantalla de Núcleo.",
        )
        for n, (t, x, marcada) in enumerate(
            [
                ("Abre el buscador", "Presiona Ctrl + K o haz clic en la lupa de arriba.", None),
                ("Escribe la cédula", "Con guiones o sin ellos: Núcleo la reconoce igual.", 0),
                (
                    "Revisa los reclamos",
                    "Antes de hablar, mira si el cliente tiene un reclamo abierto: probablemente llama por eso.",
                    2,
                ),
            ],
            start=1,
        ):
            BloqueItem.objects.create(
                bloque=pasos,
                orden=n,
                titulo=t,
                texto=x,
                imagen=self.pantalla(t, fila, marcada, nombre=f"paso-{n}.png"),
            )
        juegos = [
            (
                "acordeon",
                "Lo que trae la ficha",
                "Abre cada sección.",
                [
                    (
                        "Productos",
                        "Cuentas, tarjetas y créditos, incluidos los de otras empresas del grupo.",
                        False,
                        None,
                    ),
                    (
                        "Reclamos",
                        "Los abiertos y los cerrados de los últimos 12 meses.",
                        False,
                        None,
                    ),
                    (
                        "Historial de contactos",
                        "Cada llamada, visita y correo, con quién atendió.",
                        False,
                        None,
                    ),
                ],
                [],
            ),
            (
                "tarjetas",
                "Palabras de la ficha",
                "",
                [
                    ("Ficha única", "La pantalla con todo lo del cliente en Núcleo.", False, None),
                    (
                        "Clave dinámica",
                        "Código de seis dígitos que el cliente ve en su app.",
                        False,
                        None,
                    ),
                    (
                        "Contacto",
                        "Cada vez que el cliente habla con el banco, por cualquier canal.",
                        False,
                        None,
                    ),
                ],
                [],
            ),
            (
                "pregunta",
                "",
                "Un cliente llama y la ficha muestra un reclamo abierto por cobro duplicado. ¿Qué haces primero?",
                [
                    (
                        "Le pregunto en qué lo puedo ayudar",
                        "Está bien preguntar, pero ya tienes una pista: adelántate.",
                        False,
                        None,
                    ),
                    (
                        "Le confirmo que vi su reclamo y le cuento en qué va",
                        "Así es: el cliente siente que el banco lo conoce y la llamada se acorta.",
                        True,
                        None,
                    ),
                    (
                        "Lo derivo a reclamos",
                        "Con la ficha ya no hace falta derivar: tú puedes ver el estado.",
                        False,
                        None,
                    ),
                ],
                [],
            ),
            (
                "ordenar",
                "",
                "Ordena lo que haces al recibir una llamada.",
                [
                    ("Saludar y pedir la cédula", "", False, None),
                    ("Abrir la ficha", "", False, None),
                    ("Validar la clave dinámica", "", False, None),
                    ("Revisar reclamos abiertos", "", False, None),
                    ("Resolver la consulta", "", False, None),
                ],
                [],
            ),
            (
                "clasificar",
                "¿Se puede decir por teléfono?",
                "Reparte cada dato según si se puede informar después de validar la clave dinámica.",
                [
                    ("Saldo de la cuenta", "Sí, una vez validada la clave.", False, 1),
                    ("Estado de un reclamo", "Sí: es información del propio cliente.", False, 1),
                    ("Número completo de la tarjeta", "Nunca, ni con la clave validada.", False, 2),
                    ("Clave de internet", "Nunca: el banco jamás la pide ni la dice.", False, 2),
                ],
                ["Se puede informar", "Nunca por teléfono"],
            ),
            (
                "escenario",
                "Llamada difícil",
                "Un cliente molesto dice que es la tercera vez que llama por el mismo cobro y no quiere validar la clave dinámica porque «ya lo hizo ayer».",
                [
                    (
                        "Le doy la información igual, porque ya validó ayer",
                        "La validación vale solo para esa llamada: sin clave no hay información, aunque el cliente esté molesto.",
                        False,
                        None,
                    ),
                    (
                        "Le explico que es por su seguridad y lo ayudo a validarla",
                        "Bien: reconoces su molestia, explicas el porqué y en un minuto sigues con su reclamo.",
                        True,
                        None,
                    ),
                    (
                        "Le digo que llame más tarde",
                        "El cliente ya llamó tres veces: posponer empeora la experiencia.",
                        False,
                        None,
                    ),
                ],
                [],
            ),
        ]
        for n, (tipo, titulo, texto, items, grupos) in enumerate(juegos, start=orden + 2):
            b = Bloque.objects.create(
                leccion=leccion, orden=n, tipo=tipo, titulo=titulo, texto=texto, grupos=grupos
            )
            for k, (it, ix, ok, grupo) in enumerate(items, start=1):
                BloqueItem.objects.create(
                    bloque=b, orden=k, titulo=it, texto=ix, correcta=ok, grupo=grupo
                )
        # Page breaks: a titled screen for the screenshot, another for the steps, and
        # one after "Cruzar la grieta" that asks to solve it before going on.
        cortes = {"nota": ("La ficha por dentro", False), "documento": ("Buscar la ficha", False)}
        cortes["pregunta"] = ("", True)
        n = 0
        for b in list(leccion.bloques.order_by("orden")):
            n += 1
            Bloque.objects.filter(pk=b.pk).update(orden=n)
            if b.tipo in cortes:
                titulo, exigir = cortes.pop(b.tipo)
                n += 1
                Bloque.objects.create(
                    leccion=leccion, orden=n, tipo="corte", titulo=titulo, exigir_juego=exigir
                )
        from apps.aprendizaje.cursos import _items, block_errors

        for b in leccion.bloques.all():
            assert not block_errors(b, _items(b)), (b.tipo, block_errors(b, _items(b)))

    def climb(self, curso):
        """Enrolls cashiers and branch heads at different points of the climb. Their
        questionnaire answers (Formularios) decide who already reached the summit."""
        lecciones = list(curso.lecciones.all())
        personas = list(
            Persona.objects.filter(grupo__name__in=["Cajeros de sucursal", "Jefes de sucursal"])
        )
        aprobados = set(
            Respuesta.objects.filter(
                enlace__cuestionario=curso.evaluacion, aprobado=True
            ).values_list("enlace__persona_id", flat=True)
        )
        for n, persona in enumerate(personas):
            ins = Inscripcion.objects.create(curso=curso, persona=persona)
            if persona.pk in aprobados and n % 5 == 0:  # straight to the evaluation
                Inscripcion.objects.filter(pk=ins.pk).update(
                    iniciada_at=ago(10), directo_at=ago(10)
                )
                continue
            vistas = len(lecciones) if persona.pk in aprobados else n % len(lecciones)
            for leccion in lecciones[:vistas]:
                LeccionVista.objects.create(
                    inscripcion=ins, leccion=leccion, vista_at=ago(12 - vistas)
                )
            if vistas:
                Inscripcion.objects.filter(pk=ins.pk).update(iniciada_at=ago(12))
        for ins in Inscripcion.objects.filter(curso=curso):
            sincronizar(ins)

    def aprendizaje(self):
        Ajustes.objects.create(expedicion=True, meta_cordada=80)
        Encabezado.objects.create(
            imagen=self.banner(), texto_alternativo="Banco Altiplano · Escuela Núcleo"
        )
        caja = self.curso(
            "Operación de caja en Núcleo",
            "Todo lo que necesitas para abrir, operar y cuadrar tu caja en Núcleo desde el "
            "primer día. Al final, la evaluación de Formularios certifica que estás listo.",
            [
                ("Bienvenida a Núcleo", 5, True, [], [
                    ("texto", "Por qué cambiamos", "Núcleo reemplaza al sistema de caja que usamos hace 18 años. Desde el go-live, toda la operación de caja se hace en Núcleo: no hay vuelta atrás al sistema antiguo.\n\nLo bueno: las diferencias se ven en el momento, no al día siguiente.", []),
                    ("nota", "Ojo", "Tu usuario de Núcleo tiene doble factor. Si no lo activaste, hazlo antes de tu primer turno con el nuevo sistema.", []),
                    ("tarjetas", "Palabras nuevas", "Las vas a escuchar desde el primer día.", [
                        ("Arqueo", "Conteo del efectivo de una caja para comparar con lo registrado.", False),
                        ("Cuadre", "Cierre de la caja: lo contado contra lo que Núcleo registró.", False),
                        ("Doble factor", "Clave más un código en tu celular para entrar a Núcleo.", False),
                        ("Go-live", "El día en que Núcleo reemplaza al sistema antiguo.", False),
                    ]),
                    ("pregunta", "", "Si mañana Núcleo está lento, ¿puedes volver al sistema antiguo para atender?", [
                        ("Sí, mientras se resuelve", "El sistema antiguo quedó solo de consulta: ya no registra movimientos.", False),
                        ("No, registro un ticket en la Bitácora y aviso a mi jefe", "Así es. La mesa de ayuda prioriza los tickets de caja durante el go-live.", True),
                        ("Depende de la sucursal", "La regla es igual para todas las sucursales.", False),
                    ]),
                ]),
                ("Abrir la caja del día", 10, True, [0], [
                    ("pasos", "Apertura en cuatro pasos", "Lo haces una vez por turno, antes de atender al primer cliente.", [
                        ("Ingresa a Núcleo", "Entra con tu usuario y confirma el doble factor en tu celular.", False),
                        ("Elige tu caja", "En Caja → Apertura, selecciona tu número de caja y tu turno.", False),
                        ("Declara el fondo inicial", "Cuenta el efectivo por denominación y regístralo. Núcleo calcula el total.", False),
                        ("Confirma con tu jefe", "Tu jefe de sucursal aprueba la apertura en su pantalla. Recién ahí puedes atender.", False),
                    ]),
                    ("ordenar", "", "Ordena los pasos de la apertura, del primero al último.", [
                        ("Ingresar a Núcleo con doble factor", "", False),
                        ("Elegir la caja y el turno", "", False),
                        ("Contar y declarar el fondo inicial", "", False),
                        ("Esperar la aprobación del jefe de sucursal", "", False),
                        ("Atender al primer cliente", "", False),
                    ]),
                ]),
                ("Cuadre y diferencias", 12, True, [1], [
                    ("texto", "", "Al cierre, Núcleo compara lo que declaras con lo que registró durante el día. Si hay diferencia, la ves de inmediato y tienes que explicarla antes de cerrar.", []),
                    ("acordeon", "Preguntas frecuentes", "", [
                        ("¿Qué pasa si la diferencia es menor a $5.000?", "La registras con una nota y cierras. Tu jefe la ve en su reporte diario.", False),
                        ("¿Y si es mayor a $50.000?", "Necesita la aprobación del jefe de sucursal antes de cerrar. Adjunta el detalle de movimientos.", False),
                        ("¿Puedo cuadrar sin conexión?", "No. El cuadre se hace siempre en línea: si no hay conexión, avisa a tu jefe y registra un ticket.", False),
                    ]),
                    ("pregunta", "", "Al cierre tienes una diferencia de $62.000. ¿Quién la aprueba?", [
                        ("Yo mismo, con una nota", "Solo las diferencias menores a $5.000 se cierran con una nota.", False),
                        ("El jefe de sucursal", "Correcto: sobre $50.000 aprueba el jefe, con el detalle de movimientos adjunto.", True),
                        ("Back office, al día siguiente", "Con Núcleo ya no se espera al día siguiente: se resuelve antes de cerrar.", False),
                    ]),
                    ("clasificar", "¿Qué cambia con Núcleo?", "Reparte cada tarjeta: ¿cambia o se mantiene igual?", [
                        ("Las diferencias se ven en el momento", "Antes se veían al día siguiente.", False, 1),
                        ("El jefe aprueba diferencias sobre $50.000", "Esa regla no cambió.", False, 2),
                        ("El cuadre es siempre en línea", "Antes se podía cuadrar sin conexión.", False, 1),
                        ("Se cuenta el efectivo por denominación", "Se sigue contando igual.", False, 2),
                        ("Los arqueos quedan registrados en Caja → Arqueos", "Antes se anotaban en papel.", False, 1),
                    ], ["Cambia con Núcleo", "Se mantiene igual"]),
                    ("ordenar", "", "Ordena el cierre de una caja con diferencia.", [
                        ("Contar el efectivo por denominación", "", False),
                        ("Declarar el total en Núcleo", "", False),
                        ("Revisar la diferencia que muestra Núcleo", "", False),
                        ("Adjuntar el detalle de movimientos", "", False),
                        ("Pedir la aprobación del jefe de sucursal", "", False),
                    ]),
                ]),
                ("Arqueo sorpresa", 6, False, [1], [
                    ("texto", "", "El jefe de sucursal puede hacer un arqueo sorpresa en cualquier momento del turno. No detiene la atención por más de diez minutos.", []),
                    ("escenario", "Arqueo con fila", "Son las 12:30, tienes ocho clientes en la fila y tu jefa llega a hacer un arqueo sorpresa.", [
                        ("Le pido que vuelva más tarde", "El arqueo es sorpresa justamente para que no se pueda postergar. Tu jefa lo registra como no realizado.", False),
                        ("Pauso la atención, cuento con ella y retomo", "Bien: el arqueo no detiene la atención más de diez minutos y queda registrado en Núcleo.", True),
                        ("Sigo atendiendo mientras ella cuenta sola", "El arqueo se hace con el cajero presente: si no, el conteo no vale.", False),
                    ]),
                    ("pregunta", "", "¿Dónde se registra un arqueo sorpresa?", [
                        ("Caja → Arqueos", "Ahí queda con fecha, hora y quién lo hizo.", True),
                        ("Reportes → Cierre", "Ese reporte es del cierre del día, no de los arqueos.", False),
                        ("No se registra", "Todo arqueo queda registrado en Núcleo.", False),
                    ]),
                ]),
            ],
            impactos_=[self.imp["caja"]], evaluacion=self.caja, fecha_limite=day(12),
            montana=Montana.BARU, creado_por=self.u["valentina"],
        )  # fmt: skip
        assert not publish_errors(caja), publish_errors(caja)
        caja.estado, caja.publicado_at = EstadoCurso.PUBLICADO, ago(5)
        caja.save()
        self.climb(caja)
        ficha = self.curso(
            "Atención con la ficha única",
            "Cómo usar la ficha única del cliente para resolver en una sola llamada.",
            [
                ("La ficha en un vistazo", 15, True, [], []),  # every block type: see muestrario()
                ("Verificar la identidad", 6, True, [0], [
                    ("ordenar", "", "Ordena la verificación antes de dar un saldo por teléfono.", [
                        ("Pedir el número de cédula", "", False),
                        ("Abrir la ficha del cliente", "", False),
                        ("Validar la clave dinámica", "", False),
                        ("Informar el saldo", "", False),
                    ]),
                ]),
            ],
            impactos_=[self.imp["ficha"]], montana=Montana.CHIRRIPO, creado_por=self.u["joaquin"],
        )  # fmt: skip
        self.muestrario(ficha.lecciones.get(orden=1))
        self.out(
            f"Ascenso y Aprendizaje: 2 cursos (1 publicado, {Inscripcion.objects.count()} "
            "personas en camino) con juegos, cordadas y encabezado del banco"
        )

    # Dashboard and guide ------------------------------------------------------------------

    def dashboard(self):
        owners = ["Valentina Rojas", "Matías Fuentes (PMO)", "Ricardo Vidal"]
        for i, ind in enumerate(INDICATORS):
            IndicadorConfig.objects.create(
                key=ind.key, verde=ind.verde, amarillo=ind.amarillo,
                responsable=owners[i % 3], frecuencia=["Semanal", "Mensual", "Por etapa"][i % 3],
            )  # fmt: skip
        series = {
            "mov_comprension": [48, 61, 72],
            "for_personas": [12, 35, 58],
            "tr_usuarios_activos": [140, 310, 455],
            "tr_adopcion_30": [55, 68, 76],
            "tr_adopcion_60": [40, 57, 66],
            "tr_adopcion_90": [30, 44, 52],
            "tr_diagnostico": [2.1, 2.8, 3.4],
        }
        for key, values in series.items():
            for months_ago, value in zip((2, 1, 0), values, strict=True):
                ValorManual.objects.create(
                    key=key, fecha=day(-30 * months_ago - 3), valor=Decimal(str(value)),
                    nota="Encuesta de pulso" if key.startswith("mov") else "Reporte de Núcleo",
                    cargado_por=self.u["matias"],
                )  # fmt: skip
        ValorManual.objects.create(
            key="mov_comprension", fecha=day(-3), valor=Decimal("81"),
            grupo=self.grupo["Cajeros de sucursal"], nota="Encuesta de pulso",
            cargado_por=self.u["matias"],
        )  # fmt: skip
        self.out("Dashboard: indicadores configurados y datos externos de 3 meses")

    def guia(self):
        for name, desc, url in [
            ("Plan de gestión del cambio · Proyecto Núcleo", "Versión aprobada por el comité", "https://example.com/nucleo/plan-gestion-cambio"),
            ("Cronograma del proyecto Núcleo", "Hitos y fecha de go-live", "https://example.com/nucleo/cronograma"),
            ("Organigrama de la red de guías", "Quién acompaña a cada sucursal", "https://example.com/nucleo/red-de-guias"),
        ]:  # fmt: skip
            Documento.objects.create(nombre=name, descripcion=desc, url=url, subido_por=self.admin)
        self.out("Guía de campo: 3 documentos del cliente")
