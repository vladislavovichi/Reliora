# tg-helpdesk

Production-style starter for a Telegram helpdesk platform built with Python 3.12, `aiogram`, PostgreSQL, Redis, Poetry, and Docker.

The repository currently focuses on infrastructure and project layout:

- modular `src/` package layout with clear boundaries
- async-ready SQLAlchemy and Alembic scaffolding
- Redis client factory for future coordination and workflow primitives
- Poetry-based dependency management
- Docker, Docker Compose, pytest, Ruff, mypy, and pre-commit

Ticket workflows, persistence models, and business logic are intentionally left for later stages.

## Quick start

```bash
cp .env.example .env
poetry install
make run
```

`APP__DRY_RUN=true` is enabled by default, so the process boots, configures logging, and stays alive without starting Telegram polling.

The project uses Poetry for dependency management only. It is not configured as an installable application package at this stage.

To run the full container stack:

```bash
docker compose up --build
```

## Project layout

```text
src/
  app/             # process bootstrap and entrypoints
  bot/             # aiogram routers, handlers, middlewares
  domain/          # entities, enums, contracts
  application/     # use cases and services
  infrastructure/  # config, db, redis, logging
tests/             # test suite
alembic/           # migration environment placeholder
```
