POETRY ?= poetry
COMPOSE ?= docker compose
ALEMBIC ?= PYTHONPATH=src $(POETRY) run alembic
APP_MODULE ?= app.main

.PHONY: help install lint format typecheck test check run migrate make-migration docker-up docker-down logs up down pre-commit-install pre-commit-run

help:
	@printf "Available targets:\n"
	@printf "  install            Install project dependencies with Poetry\n"
	@printf "  lint               Run Ruff and mypy\n"
	@printf "  format             Auto-fix Ruff issues and format code\n"
	@printf "  test               Run the test suite\n"
	@printf "  check              Run lint and tests\n"
	@printf "  run                Start the application locally\n"
	@printf "  migrate            Apply Alembic migrations\n"
	@printf "  make-migration     Create a new Alembic revision (use name=...)\n"
	@printf "  docker-up          Start the Docker Compose stack\n"
	@printf "  docker-down        Stop the Docker Compose stack\n"
	@printf "  logs               Tail application logs from Docker Compose\n"
	@printf "  pre-commit-install Install pre-commit hooks\n"
	@printf "  pre-commit-run     Run pre-commit on all files\n"

install:
	$(POETRY) install

format:
	$(POETRY) run ruff check . --fix
	$(POETRY) run ruff format .

lint:
	$(POETRY) run ruff check .
	$(POETRY) run mypy src tests

typecheck:
	$(POETRY) run mypy src tests

test:
	$(POETRY) run pytest

run:
	PYTHONPATH=src $(POETRY) run python -m $(APP_MODULE)

migrate:
	$(ALEMBIC) upgrade head

make-migration:
	@test -n "$(name)" || (echo "Usage: make make-migration name=descriptive_message" && exit 1)
	$(ALEMBIC) revision --autogenerate -m "$(name)"

check: lint test

docker-up:
	$(COMPOSE) up --build

docker-down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f app

up: docker-up

down: docker-down

pre-commit-install:
	$(POETRY) run pre-commit install

pre-commit-run:
	$(POETRY) run pre-commit run --all-files
