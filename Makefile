POETRY ?= poetry
COMPOSE ?= docker compose
COMPOSE_FILE ?= ops/docker/compose.yml
PYTHON ?= python3.12
export PYTHONPATH ?= src
ALEMBIC_CONFIG ?= migrations/alembic.ini
ALEMBIC ?= $(POETRY) run alembic -c $(ALEMBIC_CONFIG)
APP_MODULE ?= app.main
BACKEND_MODULE ?= backend.main
AI_SERVICE_MODULE ?= ai_service.main
FULL_SCRIPT ?= ops/docker/full.sh
FULL_SERVICES ?= postgres redis ai-service backend bot
FULL_TIMEOUT ?= 180
BACKEND_PROTO_SRC ?= src/backend/proto/helpdesk.proto
BACKEND_PROTO_INCLUDE ?= src/backend/proto
BACKEND_PROTO_OUT ?= src/backend/grpc/generated
AI_PROTO_SRC ?= src/ai_service/proto/ai_service.proto
AI_PROTO_INCLUDE ?= src/ai_service/proto
AI_PROTO_OUT ?= src/ai_service/grpc/generated

define ensure_poetry_env
	@if ! command -v "$(PYTHON)" >/dev/null 2>&1; then \
		echo "Python 3.12 is required for local Poetry commands, but '$(PYTHON)' was not found."; \
		echo "Install Python 3.12, then run:"; \
		echo "  poetry env use $(PYTHON)"; \
		echo "  poetry install"; \
		exit 1; \
	fi
endef

.PHONY: help install lint format typecheck test proto proto-check check ci health health-backend health-ai run run-backend run-ai run-bot migrate migration-check make-migration docker-up docker-down full full-down logs logs-ai up down pre-commit-install pre-commit-run

help:
	@printf "Available targets:\n"
	@printf "  install            Install project dependencies with Poetry\n"
	@printf "  lint               Run Ruff and mypy\n"
	@printf "  format             Auto-fix Ruff issues and format code\n"
	@printf "  typecheck          Run mypy\n"
	@printf "  test               Run the test suite\n"
	@printf "  proto              Regenerate gRPC Python stubs from proto\n"
	@printf "  proto-check        Verify that generated gRPC stubs are up to date\n"
	@printf "  check              Run lint and tests\n"
	@printf "  ci                 Run lint, typing, tests, proto-check, and migration consistency\n"
	@printf "  health             Run the bot-side health check\n"
	@printf "  health-backend     Run the backend-side health check\n"
	@printf "  health-ai          Run the ai-service health check\n"
	@printf "  run                Start the Telegram bot runtime locally\n"
	@printf "  run-backend        Start the backend gRPC service locally\n"
	@printf "  run-ai             Start the ai-service gRPC runtime locally\n"
	@printf "  run-bot            Start the Telegram bot runtime locally\n"
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

proto:
	$(call ensure_poetry_env)
	$(POETRY) run python -m grpc_tools.protoc -I $(BACKEND_PROTO_INCLUDE) --python_out=$(BACKEND_PROTO_OUT) --grpc_python_out=$(BACKEND_PROTO_OUT) $(BACKEND_PROTO_SRC)
	$(POETRY) run python -c "from pathlib import Path; path = Path('$(BACKEND_PROTO_OUT)/helpdesk_pb2_grpc.py'); path.write_text(path.read_text().replace('import helpdesk_pb2 as helpdesk__pb2', 'from . import helpdesk_pb2 as helpdesk__pb2'))"
	$(POETRY) run python -m grpc_tools.protoc -I $(AI_PROTO_INCLUDE) --python_out=$(AI_PROTO_OUT) --grpc_python_out=$(AI_PROTO_OUT) $(AI_PROTO_SRC)
	$(POETRY) run python -c "from pathlib import Path; path = Path('$(AI_PROTO_OUT)/ai_service_pb2_grpc.py'); path.write_text(path.read_text().replace('import ai_service_pb2 as ai__service__pb2', 'from . import ai_service_pb2 as ai__service__pb2'))"

proto-check: proto
	git diff --exit-code -- $(BACKEND_PROTO_OUT) $(AI_PROTO_OUT)

health:
	$(call ensure_poetry_env)
	$(POETRY) run python -m app.healthcheck

health-backend:
	$(call ensure_poetry_env)
	$(POETRY) run python -m backend.healthcheck

health-ai:
	$(call ensure_poetry_env)
	$(POETRY) run python -m ai_service.healthcheck

migration-check:
	$(call ensure_poetry_env)
	$(ALEMBIC) upgrade head
	$(ALEMBIC) check

run:
	$(MAKE) run-bot

run-backend:
	$(call ensure_poetry_env)
	$(POETRY) run python -m $(BACKEND_MODULE)

run-ai:
	$(call ensure_poetry_env)
	$(POETRY) run python -m $(AI_SERVICE_MODULE)

run-bot:
	$(call ensure_poetry_env)
	$(POETRY) run python -m $(APP_MODULE)

migrate:
	$(call ensure_poetry_env)
	$(ALEMBIC) upgrade head

make-migration:
	@test -n "$(name)" || (echo "Usage: make make-migration name=descriptive_message" && exit 1)
	$(call ensure_poetry_env)
	$(ALEMBIC) revision --autogenerate -m "$(name)"

check: lint typecheck test

ci: lint typecheck test proto-check migration-check

docker-up:
	$(COMPOSE) -f $(COMPOSE_FILE) up --build -d

docker-down:
	$(COMPOSE) -f $(COMPOSE_FILE) down

full:
	COMPOSE="$(COMPOSE) -f $(COMPOSE_FILE)" FULL_SERVICES="$(FULL_SERVICES)" FULL_TIMEOUT="$(FULL_TIMEOUT)" sh $(FULL_SCRIPT)

full-down: docker-down

logs:
	$(COMPOSE) -f $(COMPOSE_FILE) logs -f ai-service backend bot

logs-ai:
	$(COMPOSE) -f $(COMPOSE_FILE) logs -f ai-service

up: docker-up

down: docker-down

pre-commit-install:
	$(call ensure_poetry_env)
	$(POETRY) run pre-commit install

pre-commit-run:
	$(call ensure_poetry_env)
	$(POETRY) run pre-commit run --all-files
