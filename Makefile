POETRY ?= poetry
COMPOSE ?= docker compose
COMPOSE_FILE ?= ops/docker/compose.yml
PYTHON ?= python3.12
export PYTHONPATH ?= src
ALEMBIC_CONFIG ?= migrations/alembic.ini
ALEMBIC ?= $(POETRY) run alembic -c $(ALEMBIC_CONFIG)
APP_MODULE ?= app.main
FULL_SCRIPT ?= ops/docker/full.sh
FULL_SERVICES ?= postgres redis app
FULL_TIMEOUT ?= 180

define ensure_poetry_env
	@if ! command -v "$(PYTHON)" >/dev/null 2>&1; then \
		echo "Python 3.12 is required for local Poetry commands, but '$(PYTHON)' was not found."; \
		echo "Install Python 3.12, then run:"; \
		echo "  poetry env use $(PYTHON)"; \
		echo "  poetry install"; \
		exit 1; \
	fi
endef

.PHONY: help install lint format typecheck test check ci health run migrate migration-check make-migration docker-up docker-down full full-down logs up down pre-commit-install pre-commit-run

help:
	@printf "Available targets:\n"
	@printf "  install            Install project dependencies with Poetry\n"
	@printf "  lint               Run Ruff and mypy\n"
	@printf "  format             Auto-fix Ruff issues and format code\n"
	@printf "  typecheck          Run mypy\n"
	@printf "  test               Run the test suite\n"
	@printf "  check              Run lint and tests\n"
	@printf "  ci                 Run lint, tests, and migration consistency checks\n"
	@printf "  health             Run a local dependency and runtime health check\n"
	@printf "  run                Start the application locally\n"
	@printf "  migrate            Apply Alembic migrations\n"
	@printf "  migration-check    Verify that migrations match the SQLAlchemy metadata\n"
	@printf "  make-migration     Create a new Alembic revision (use name=...)\n"
	@printf "  docker-up          Start the Docker Compose stack in the background\n"
	@printf "  docker-down        Stop the Docker Compose stack\n"
	@printf "  full               Build, start, and verify the full Docker Compose stack\n"
	@printf "  full-down          Stop the full Docker Compose stack\n"
	@printf "  logs               Tail application logs from Docker Compose\n"
	@printf "  pre-commit-install Install pre-commit hooks\n"
	@printf "  pre-commit-run     Run pre-commit on all files\n"

install:
	$(call ensure_poetry_env)
	$(POETRY) install

format:
	$(call ensure_poetry_env)
	$(POETRY) run ruff check . --fix
	$(POETRY) run ruff format .

lint:
	$(call ensure_poetry_env)
	$(POETRY) run ruff check .
	$(POETRY) run mypy src tests

typecheck:
	$(call ensure_poetry_env)
	$(POETRY) run mypy src tests

test:
	$(call ensure_poetry_env)
	$(POETRY) run pytest

health:
	$(call ensure_poetry_env)
	$(POETRY) run python -m app.healthcheck

migration-check:
	$(call ensure_poetry_env)
	$(ALEMBIC) upgrade head
	$(ALEMBIC) check

run:
	$(call ensure_poetry_env)
	$(POETRY) run python -m $(APP_MODULE)

migrate:
	$(call ensure_poetry_env)
	$(ALEMBIC) upgrade head

make-migration:
	@test -n "$(name)" || (echo "Usage: make make-migration name=descriptive_message" && exit 1)
	$(call ensure_poetry_env)
	$(ALEMBIC) revision --autogenerate -m "$(name)"

check: lint test

ci: lint test migration-check

docker-up:
	$(COMPOSE) -f $(COMPOSE_FILE) up --build -d

docker-down:
	$(COMPOSE) -f $(COMPOSE_FILE) down

full:
	COMPOSE="$(COMPOSE) -f $(COMPOSE_FILE)" FULL_SERVICES="$(FULL_SERVICES)" FULL_TIMEOUT="$(FULL_TIMEOUT)" sh $(FULL_SCRIPT)

full-down: docker-down

logs:
	$(COMPOSE) -f $(COMPOSE_FILE) logs -f app

up: docker-up

down: docker-down

pre-commit-install:
	$(call ensure_poetry_env)
	$(POETRY) run pre-commit install

pre-commit-run:
	$(call ensure_poetry_env)
	$(POETRY) run pre-commit run --all-files
