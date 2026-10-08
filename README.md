# Cordada

Plataforma de gestión del cambio. Requisitos: `docs/Cordada-Parte-B-Requisitos-Plataforma.md`.

## Desarrollo local

Requiere Docker. El primer `make` crea `.env` a partir de `.env.example`.

```sh
make up                              # app en http://localhost:8000, Mailpit en http://localhost:8025
make platform-admin email=tu@correo   # administrador de plataforma (pide contraseña)
make test                            # pytest dentro del contenedor
make lint                            # ruff
make makemigrations / make migrate
make backup                          # pg_dump a ./backups
make down
```

Dependencias con `uv`: editar `pyproject.toml`, luego `make lock && make build`.

## Clientes y accesos

- **Administrador de plataforma** (`/plataforma/`): crea y configura clientes, activa
  módulos e invita personas con un rol. No ve los datos de los clientes; para trabajar
  dentro de uno, se invita a sí mismo con un rol.
- Las invitaciones llegan por correo (en local, a Mailpit) y vencen en 7 días.
- Cada cliente vive en `/c/<identificador>/`. Quien no es miembro recibe 404.
- Roles y permisos por módulo: `apps/core/permissions.py` (Parte B §2).
- Modelos de un cliente: heredar de `apps.core.tenancy.TenantScopedModel`. Si declaran
  `class Meta`, debe heredar de `TenantScopedModel.Meta`.
- `/admin/` (admin de Django) queda solo para superusuarios técnicos
  (`make manage cmd=createsuperuser`).

## Catálogos y cálculos

- **Del sistema** (`/plataforma/catalogos/`): tiempos, tipos de impacto, origen, categorías de
  ticket, tipo de cambio en el conocimiento, evidencia de cierre y las escalas. Se cargan con la
  migración `catalogs/0002`. El `código` es estable (el código fuente puede depender de él);
  nombre, ayuda y orden se editan. En un modelo: `SystemCatalogField(SystemCatalog.TIPO_IMPACTO)`.
- **Del cliente** (`/c/<cliente>/configuracion/`, rol Administración): grupos impactados,
  unidades (área, oficina, sucursal, departamento), cargos y categorías de responsable.
- **Riesgo y prioridad** (§3.4): `apps/scoring/rules.py`, probado contra las tablas completas.
- Los estados de cada flujo (impacto, actividad, ticket…) se definen en código en su módulo.

## Matriz de Impactos

- `/c/<cliente>/matriz/`. Quien edita la matriz (Administración, Equipo de cambio) ve todo y
  usa el formulario completo; quien propone (Capitán, Guía, Equipo técnico) ve solo sus
  propuestas y un formulario corto, con "grupo sugerido" si el grupo no existe.
- Ciclo de vida y campos obligatorios para evaluar: `apps/matriz/workflow.py`
  (`REQUIRED_FOR_EVALUATION`, pendiente de la lista final §13.1). Cada cambio de estado queda
  en `Transicion`.
- Riesgo y prioridad se recalculan al guardar; el ajuste manual exige justificación.
- Adjuntos: solo se descargan por la vista con permisos (no hay `/media/` público).
- Fotos por etapa: copia completa de la matriz en JSON, exportable a Excel.

## Ruta

- `/c/<cliente>/ruta/`: actividades de los cuatro frentes con lo planificado y lo ejecutado en el
  mismo registro. Se vinculan a impactos y grupos; sin impacto, la actividad es **huérfana**; un
  impacto activo sin actividades es **descubierto** (filtro en la matriz).
- Cumplimiento calculado (`apps/ruta/models.py: cumplimiento`): a tiempo, con retraso,
  no realizada (vencida), no planificada, pendiente.
- Capitanes ven solo las actividades de sus grupos: se asignan en Configuración → Personas.
- Informe de cumplimiento por etapa o por mes, en pantalla y en PDF (WeasyPrint).
- Adjuntos compartidos: `apps/core/attachments.py`.

## Tablero y dependencias

- `/c/<cliente>/matriz/tablero/`: kanban por estado. Arrastrar cambia el estado con las mismas
  reglas del ciclo de vida (`static/js/tablero.js` + `matriz:mover`).
- Dependencias "Depende de" (`apps/matriz/dependencias.py`): solo avisan, nunca bloquean el
  ciclo de vida. Un impacto está **bloqueado** si depende de uno abierto (Propuesto, Evaluado,
  En atención, Reabierto). Solo el rol Equipo de cambio crea o quita dependencias; no se
  permiten ciclos.

## Bitácora

- `/c/<cliente>/bitacora/`: tickets con flujo nuevo → en clasificación → validado → derivado a
  TI → resuelto → cerrado (`apps/bitacora/workflow.py`; cada paso indica el permiso que exige).
- Fallo grave técnico: se deriva a TI desde Nuevo y se valida en paralelo. Solo los técnicos van
  a TI; TI puede devolverlos con motivo.
- Primera respuesta y resolución se registran solas con los cambios de estado.
- Vista TI en vivo (`/bitacora/ti/`, refresco cada 15 s), métricas (por tipo, por grupo cada 100
  personas, tiempos, recurrencia) y exportación a Excel.
- Un ticket de impacto no anticipado propone un impacto en la matriz. Si existe un origen con
  código `bitacora` en el catálogo de origen, se asigna automáticamente.
