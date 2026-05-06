POETRY ?= poetry
COMPOSE ?= docker compose
COMPOSE_FILES ?= -f ops/docker/compose.yml -f ops/docker/compose.dev.yml
PYTHON ?= python3.12
export PYTHONPATH ?= src
ALEMBIC_CONFIG ?= migrations/alembic.ini
ALEMBIC ?= $(POETRY) run alembic -c $(ALEMBIC_CONFIG)
APP_MODULE ?= app.main
BACKEND_MODULE ?= backend.main
AI_SERVICE_MODULE ?= ai_service.main
MINI_APP_MODULE ?= mini_app.main
CLOUDFLARED_BIN ?= cloudflared
MINI_APP_TUNNEL_HOST ?= 127.0.0.1
MINI_APP_TUNNEL_PORT ?= 8088
MINI_APP_TUNNEL_URL ?= http://$(MINI_APP_TUNNEL_HOST):$(MINI_APP_TUNNEL_PORT)
ENV_FILE ?= .env.local
export RELIORA_ENV_FILE ?= ../../$(ENV_FILE)
FULL_SCRIPT ?= ops/docker/full.sh
FULL_SERVICES ?= postgres redis ai-service backend bot mini-app
FULL_TIMEOUT ?= 180
STACK_HEALTH_SCRIPT ?= ops/scripts/stack_health.sh
SMOKE_SCRIPT ?= /app/ops/scripts/smoke_check.py
BACKUP_DB_SCRIPT ?= ops/scripts/backup_db.sh
RESTORE_DB_SCRIPT ?= ops/scripts/restore_db.sh
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

define port_is_available
python3 -c 'import socket, sys; sock = socket.socket(); sock.settimeout(0.2); result = sock.connect_ex(("127.0.0.1", int(sys.argv[1]))); sock.close(); sys.exit(0 if result != 0 else 1)' "$(1)"
endef

.PHONY: help install lint format typecheck test repo-hygiene architecture-boundaries proto proto-check check ci health health-bot health-backend health-ai health-mini-app smoke ai-smoke run run-backend run-ai run-bot run-mini-app run-mini-app-cloudflared migrate migrate-stack migration-check make-migration docker-up docker-down restart ps full full-cloudflared full-down logs logs-bot logs-backend logs-ai logs-mini-app backup-db restore-db up down pre-commit-install pre-commit-run

COMPOSE_CMD = $(COMPOSE) --env-file $(ENV_FILE) $(COMPOSE_FILES)

help:
	@printf "Available targets:\n"
	@printf "  install            Install project dependencies with Poetry\n"
	@printf "  lint               Run Ruff\n"
	@printf "  format             Auto-fix Ruff issues and format code\n"
	@printf "  typecheck          Run mypy\n"
	@printf "  test               Run the test suite\n"
	@printf "  repo-hygiene       Verify generated/cache artifacts are not tracked\n"
	@printf "  architecture-boundaries  Verify bot/backend import boundaries\n"
	@printf "  proto              Regenerate gRPC Python stubs from proto\n"
	@printf "  proto-check        Verify that generated gRPC stubs are up to date\n"
	@printf "  check              Run lint, typing, and tests\n"
	@printf "  ci                 Run check, proto-check, and migration consistency\n"
	@printf "  health             Show Docker Compose stack health\n"
	@printf "  health-bot         Run the bot-side health check locally\n"
	@printf "  health-backend     Run the backend-side health check\n"
	@printf "  health-ai          Run the ai-service health check\n"
	@printf "  smoke             Run the operational smoke-check against the running stack\n"
	@printf "  ai-smoke           Verify a real AI completion through ai-service gRPC\n"
	@printf "  run                Start the Telegram bot runtime locally\n"
	@printf "  run-backend        Start the backend gRPC service locally\n"
	@printf "  run-ai             Start the ai-service gRPC runtime locally\n"
	@printf "  run-bot            Start the Telegram bot runtime locally\n"
	@printf "  run-mini-app       Start the Telegram Mini App gateway locally\n"
	@printf "  run-mini-app-cloudflared  Expose the local Mini App over cloudflared HTTPS tunnel\n"
	@printf "  migrate            Apply Alembic migrations\n"
	@printf "  migrate-stack      Apply Alembic migrations inside the backend container\n"
	@printf "  migration-check    Verify that migrations match the SQLAlchemy metadata\n"
	@printf "  make-migration     Create a new Alembic revision (use name=...)\n"
	@printf "  docker-up          Start the Docker Compose stack in the background\n"
	@printf "  docker-down        Stop the Docker Compose stack\n"
	@printf "  restart            Restart the Docker Compose stack\n"
	@printf "  ps                 Show Docker Compose service state\n"
	@printf "  full               Build, start, and verify the full Docker Compose stack\n"
	@printf "  full-cloudflared   Start the full Docker Compose stack and expose Mini App over cloudflared\n"
	@printf "  full-down          Stop the full Docker Compose stack\n"
	@printf "  logs               Tail application logs from Docker Compose\n"
	@printf "  logs-bot           Tail bot logs from Docker Compose\n"
	@printf "  logs-backend       Tail backend logs from Docker Compose\n"
	@printf "  logs-mini-app      Tail Mini App logs from Docker Compose\n"
	@printf "  pre-commit-install Install pre-commit hooks\n"
	@printf "  pre-commit-run     Run pre-commit on all files\n"
	@printf "  backup-db          Create a PostgreSQL logical backup from the running stack\n"
	@printf "  restore-db         Restore PostgreSQL from BACKUP_PATH=/path/to/file.dump\n"

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

typecheck:
	$(call ensure_poetry_env)
	$(POETRY) run mypy src tests

test:
	$(call ensure_poetry_env)
	$(POETRY) run pytest

repo-hygiene:
	$(call ensure_poetry_env)
	$(POETRY) run python ops/scripts/check_repo_hygiene.py

architecture-boundaries:
	$(call ensure_poetry_env)
	$(POETRY) run python ops/scripts/check_architecture_boundaries.py

proto:
	$(call ensure_poetry_env)
	$(POETRY) run python -m grpc_tools.protoc -I $(BACKEND_PROTO_INCLUDE) --python_out=$(BACKEND_PROTO_OUT) --grpc_python_out=$(BACKEND_PROTO_OUT) $(BACKEND_PROTO_SRC)
	$(POETRY) run python -c "from pathlib import Path; path = Path('$(BACKEND_PROTO_OUT)/helpdesk_pb2_grpc.py'); path.write_text(path.read_text().replace('import helpdesk_pb2 as helpdesk__pb2', 'from . import helpdesk_pb2 as helpdesk__pb2'))"
	$(POETRY) run python -m grpc_tools.protoc -I $(AI_PROTO_INCLUDE) --python_out=$(AI_PROTO_OUT) --grpc_python_out=$(AI_PROTO_OUT) $(AI_PROTO_SRC)
	$(POETRY) run python -c "from pathlib import Path; path = Path('$(AI_PROTO_OUT)/ai_service_pb2_grpc.py'); path.write_text(path.read_text().replace('import ai_service_pb2 as ai__service__pb2', 'from . import ai_service_pb2 as ai__service__pb2'))"

proto-check: proto
	git diff --exit-code -- $(BACKEND_PROTO_OUT) $(AI_PROTO_OUT)

health-bot:
	$(call ensure_poetry_env)
	$(POETRY) run python -m app.healthcheck

health:
	COMPOSE="$(COMPOSE_CMD)" sh $(STACK_HEALTH_SCRIPT)

health-backend:
	$(call ensure_poetry_env)
	$(POETRY) run python -m backend.healthcheck

health-ai:
	$(call ensure_poetry_env)
	$(POETRY) run python -m ai_service.healthcheck

health-mini-app:
	$(call ensure_poetry_env)
	$(POETRY) run python -m mini_app.healthcheck

ai-smoke:
	$(call ensure_poetry_env)
	$(POETRY) run python ops/scripts/ai_smoke_check.py

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

run-mini-app:
	$(call ensure_poetry_env)
	$(POETRY) run python -m $(MINI_APP_MODULE)

run-mini-app-cloudflared:
	@set -eu; \
	if command -v "$(CLOUDFLARED_BIN)" >/dev/null 2>&1; then \
		cloudflared_bin="$(CLOUDFLARED_BIN)"; \
	elif [ -x /tmp/cloudflared ]; then \
		cloudflared_bin="/tmp/cloudflared"; \
	else \
		echo "cloudflared not found. Install it or place a standalone binary at /tmp/cloudflared."; \
		echo "Then run: make run-mini-app-cloudflared"; \
		exit 1; \
	fi; \
	log_file="$$(mktemp /tmp/helpdesk-cloudflared.XXXXXX.log)"; \
	trap 'status="$$?"; if [ -n "$${tail_pid:-}" ]; then kill "$$tail_pid" 2>/dev/null || true; wait "$$tail_pid" 2>/dev/null || true; fi; if [ -n "$${cloudflared_pid:-}" ]; then kill "$$cloudflared_pid" 2>/dev/null || true; wait "$$cloudflared_pid" 2>/dev/null || true; fi; rm -f "$$log_file"; exit "$$status"' INT TERM EXIT; \
	"$$cloudflared_bin" tunnel --url "$(MINI_APP_TUNNEL_URL)" --no-autoupdate >"$$log_file" 2>&1 & \
	cloudflared_pid="$$!"; \
	public_url=""; \
	attempt=0; \
	while [ "$$attempt" -lt 60 ]; do \
		if ! kill -0 "$$cloudflared_pid" 2>/dev/null; then \
			echo "cloudflared exited before publishing a public URL."; \
			cat "$$log_file"; \
			exit 1; \
		fi; \
		public_url="$$(awk 'match($$0, /https:\/\/[-a-zA-Z0-9.]*trycloudflare.com/) { print substr($$0, RSTART, RLENGTH); exit }' "$$log_file")"; \
		if [ -n "$$public_url" ]; then \
			break; \
		fi; \
		attempt="$$((attempt + 1))"; \
		sleep 1; \
	done; \
	if [ -z "$$public_url" ]; then \
		echo "cloudflared did not publish a public URL within 60 seconds."; \
		cat "$$log_file"; \
		exit 1; \
	fi; \
	if [ -f "$(ENV_FILE)" ] && grep -q '^MINI_APP__PUBLIC_URL=' "$(ENV_FILE)"; then \
		sed -i "s#^MINI_APP__PUBLIC_URL=.*#MINI_APP__PUBLIC_URL=$$public_url#" "$(ENV_FILE)"; \
	else \
		printf '\nMINI_APP__PUBLIC_URL=%s\n' "$$public_url" >> "$(ENV_FILE)"; \
	fi; \
	printf '%s\n' "Tunnel is ready: $$public_url"; \
	printf '%s\n' "Updated $(ENV_FILE): MINI_APP__PUBLIC_URL=$$public_url"; \
	compose_has_consumers=0; \
	for service in bot mini-app; do \
		if [ -n "$$($(COMPOSE_CMD) ps -q $$service 2>/dev/null || true)" ]; then \
			compose_has_consumers=1; \
		fi; \
	done; \
	if [ "$$compose_has_consumers" -eq 1 ]; then \
		printf '%s\n' "Restarting docker services so they pick up the new MINI_APP__PUBLIC_URL..."; \
		MINI_APP_EXPOSE_PORT="$(MINI_APP_TUNNEL_PORT)" $(COMPOSE_CMD) up -d bot mini-app >/dev/null; \
		printf '%s\n' "Docker services restarted: bot, mini-app"; \
	else \
		printf '%s\n' "Restart the bot so Telegram buttons use the new Mini App URL."; \
	fi; \
	tail -n +1 -f "$$log_file" & \
	tail_pid="$$!"; \
	wait "$$cloudflared_pid"

migrate:
	$(call ensure_poetry_env)
	$(ALEMBIC) upgrade head

migrate-stack:
	$(COMPOSE_CMD) run --rm backend alembic -c migrations/alembic.ini upgrade head

make-migration:
	@test -n "$(name)" || (echo "Usage: make make-migration name=descriptive_message" && exit 1)
	$(call ensure_poetry_env)
	$(ALEMBIC) revision --autogenerate -m "$(name)"

check: repo-hygiene architecture-boundaries lint typecheck test

ci: check proto-check migration-check

docker-up:
	$(COMPOSE_CMD) up --build -d

docker-down:
	$(COMPOSE_CMD) down

restart:
	$(COMPOSE_CMD) restart

ps:
	$(COMPOSE_CMD) ps

full:
	COMPOSE="$(COMPOSE_CMD)" MINI_APP_EXPOSE_PORT="$(MINI_APP_EXPOSE_PORT)" FULL_SERVICES="$(FULL_SERVICES)" FULL_TIMEOUT="$(FULL_TIMEOUT)" sh $(FULL_SCRIPT)

full-cloudflared:
	@set -eu; \
	desired_port="$${MINI_APP_EXPOSE_PORT:-$$(awk -F= '/^MINI_APP_EXPOSE_PORT=/{print $$2; exit}' "$(ENV_FILE)" 2>/dev/null)}"; \
	if [ -z "$$desired_port" ]; then \
		desired_port="$(MINI_APP_TUNNEL_PORT)"; \
	fi; \
	mini_app_port="$$desired_port"; \
	while ! $(call port_is_available,$$mini_app_port); do \
		mini_app_port="$$((mini_app_port + 1))"; \
	done; \
	if [ "$$mini_app_port" != "$$desired_port" ]; then \
		printf '%s\n' "Port $$desired_port is busy. Using $$mini_app_port for docker mini-app and cloudflared."; \
	fi; \
	$(MAKE) full MINI_APP_EXPOSE_PORT="$$mini_app_port" && \
	$(MAKE) run-mini-app-cloudflared MINI_APP_TUNNEL_PORT="$$mini_app_port"

full-down: docker-down

logs:
	$(COMPOSE_CMD) logs -f ai-service backend bot mini-app

logs-bot:
	$(COMPOSE_CMD) logs -f bot

logs-backend:
	$(COMPOSE_CMD) logs -f backend

logs-ai:
	$(COMPOSE_CMD) logs -f ai-service

logs-mini-app:
	$(COMPOSE_CMD) logs -f mini-app

smoke:
	$(COMPOSE_CMD) run --rm --no-deps backend python $(SMOKE_SCRIPT)

backup-db:
	COMPOSE="$(COMPOSE_CMD)" sh $(BACKUP_DB_SCRIPT)

restore-db:
	COMPOSE="$(COMPOSE_CMD)" BACKUP_PATH="$(BACKUP_PATH)" sh $(RESTORE_DB_SCRIPT)

up: docker-up

down: docker-down

pre-commit-install:
	$(call ensure_poetry_env)
	$(POETRY) run pre-commit install

pre-commit-run:
	$(call ensure_poetry_env)
	$(POETRY) run pre-commit run --all-files
