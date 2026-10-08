# Cordada

Plataforma de gestión del cambio. Requisitos: `docs/Cordada-Parte-B-Requisitos-Plataforma.md`.

## Desarrollo local

Requiere Docker. El primer `make` crea `.env` a partir de `.env.example`.

```sh
make up                              # app en http://localhost:8000, Mailpit en http://localhost:8025
make manage cmd="createsuperuser"    # usuario para /admin/
make test                            # pytest dentro del contenedor
make lint                            # ruff
make makemigrations / make migrate
make backup                          # pg_dump a ./backups
make down
```

Dependencias con `uv`: editar `pyproject.toml`, luego `make lock && make build`.
