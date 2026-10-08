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
