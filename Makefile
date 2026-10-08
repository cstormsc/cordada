COMPOSE = docker compose
RUN = $(COMPOSE) run --rm -e RUN_MIGRATIONS=0 web

.PHONY: up down build logs shell dbshell manage makemigrations migrate test lint lock backup

.env:
	cp .env.example .env

up: .env
	$(COMPOSE) up --build -d
	@echo "App: http://localhost:8000  ·  Mailpit: http://localhost:8025"

down:
	$(COMPOSE) down

build: .env
	$(COMPOSE) build

logs:
	$(COMPOSE) logs -f web

shell: .env
	$(RUN) python manage.py shell

dbshell: .env
	$(COMPOSE) exec db sh -c 'psql -U $$POSTGRES_USER -d $$POSTGRES_DB'

manage: .env  ## make manage cmd="createsuperuser"
	$(RUN) python manage.py $(cmd)

makemigrations: .env
	$(RUN) python manage.py makemigrations

migrate: .env
	$(RUN) python manage.py migrate

test: .env
	$(RUN) pytest $(args)

lint: .env
	$(RUN) ruff check .

lock:
	docker run --rm -v "$(CURDIR)":/app -w /app ghcr.io/astral-sh/uv:0.8-python3.13-bookworm-slim uv lock

backup: .env
	mkdir -p backups
	$(COMPOSE) exec -T db sh -c 'pg_dump -U $$POSTGRES_USER -d $$POSTGRES_DB -Fc' > backups/cordada-$$(date +%Y%m%d-%H%M%S).dump
