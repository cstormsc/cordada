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
