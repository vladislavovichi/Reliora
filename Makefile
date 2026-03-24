POETRY ?= poetry
COMPOSE ?= docker compose

.PHONY: install format lint typecheck test run up down logs pre-commit

install:
	$(POETRY) install

format:
	$(POETRY) run ruff check . --fix
	$(POETRY) run ruff format .

lint:
	$(POETRY) run ruff check .

typecheck:
	$(POETRY) run mypy src tests

test:
	$(POETRY) run pytest

run:
	PYTHONPATH=src $(POETRY) run python -m app.main

up:
	$(COMPOSE) up --build

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f app

pre-commit:
	$(POETRY) run pre-commit install
