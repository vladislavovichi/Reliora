# Reliora

`Reliora` — Telegram helpdesk для клиентской поддержки внутри одного бота. Проект принимает обращения, ведет живой диалог между клиентом и оператором, управляет очередью, ролями, макросами, тегами и операционной диагностикой.

## Что это за проект

Репозиторий собран как production-oriented backend с явным `src/` layout:

- `src/bot` отвечает за Telegram UX, тексты, клавиатуры и обработку update'ов;
- `src/application` собирает продуктовые сценарии и orchestration;
- `src/domain` хранит сущности, правила и контракты;
- `src/infrastructure` инкапсулирует PostgreSQL, Redis, конфигурацию и logging;
- `src/app` поднимает runtime, bootstrap и health-проверки.

Операционные артефакты вынесены отдельно:

- `ops/docker/` — Dockerfile, Compose и startup-скрипты;
- `ops/env/` — расширенные шаблоны окружения;
- `migrations/` — Alembic-окружение и ревизии.

## Возможности

- создание заявки из первого сообщения клиента;
- продолжение переписки в открытой заявке;
- очередь оператора с пагинацией;
- активный контекст заявки для live-диалога;
- эскалация, закрытие и переназначение;
- макросы и теги;
- статистика и диагностические проверки;
- роли `user`, `operator`, `super_admin`;
- Redis-backed FSM, rate limiting и runtime locks.

## Архитектура

Направление зависимостей:

```text
bot -> application -> domain/contracts -> infrastructure
```

Принципы слоя:

- `bot` не принимает бизнес-решения и не работает с raw DB/session;
- `application` не зависит от Telegram presentation;
- `infrastructure` не определяет продуктовые workflow-правила;
- тексты, форматтеры и клавиатуры остаются отдельным presentation-слоем.

## Роли и сценарии

**Пользователь**

- пишет в бот;
- получает подтверждение создания заявки;
- продолжает диалог;
- может завершить заявку из клиентской карточки.

**Оператор**

- берет заявки из очереди;
- ведет активный диалог;
- применяет макросы;
- меняет теги;
- закрывает, эскалирует и переназначает обращения;
- смотрит статистику.

**Суперадминистратор**

- имеет все возможности оператора;
- управляет операторами;
- управляет библиотекой макросов.

Суперадминистраторы задаются через:

```dotenv
AUTHORIZATION__SUPER_ADMIN_TELEGRAM_USER_IDS=12345,67890
```

## Быстрый старт

Требования:

- Python `3.12+`
- Poetry
- PostgreSQL и Redis, либо Docker Compose
- локальный `.env`

Базовый локальный старт:

```bash
cp .env.example .env
make install
make migrate
make health
make run
```

Если нужен bootstrap без Telegram polling:

```dotenv
APP__DRY_RUN=true
```

Фактический entrypoint:

```bash
PYTHONPATH=src poetry run python -m app.main
```

## Запуск через Docker

Полный happy-path запуск:

```bash
make full
```

Базовые команды:

```bash
make docker-up
make logs
make docker-down
```

Root-level команды остаются короткими, хотя Docker-инфраструктура хранится в `ops/docker/`.

## Конфигурация

Для обычного старта достаточно корневого шаблона:

```bash
cp .env.example .env
```

Он содержит минимальный набор переменных для локального запуска.

Расширенный шаблон с Docker-портами и дополнительными runtime-настройками:

```text
ops/env/local.env.example
```

Основные группы настроек:

- `app`
- `bot`
- `authorization`
- `database`
- `redis`
- `logging`

Минимальный набор:

```dotenv
APP__NAME=tg-helpdesk
APP__ENVIRONMENT=dev
APP__DRY_RUN=true

BOT__TOKEN=

AUTHORIZATION__SUPER_ADMIN_TELEGRAM_USER_IDS=123456789

DATABASE__HOST=postgres
DATABASE__PORT=5432
DATABASE__USER=helpdesk
DATABASE__PASSWORD=helpdesk
DATABASE__DATABASE=helpdesk

REDIS__HOST=redis
REDIS__PORT=6379
REDIS__DB=0

LOGGING__LEVEL=INFO
LOGGING__STRUCTURED=true
```

## Миграции

Alembic-конфиг хранится в `migrations/alembic.ini`.

Основные команды:

```bash
make migrate
make migration-check
make make-migration name=add_some_change
```

Прямые вызовы:

```bash
poetry run alembic -c migrations/alembic.ini current
poetry run alembic -c migrations/alembic.ini history
poetry run alembic -c migrations/alembic.ini upgrade head
```

## Тесты и качество

```bash
make format
make lint
make typecheck
make test
make check
make ci
```

Pre-commit:

```bash
make pre-commit-install
make pre-commit-run
```

## Make-команды

`Makefile` остается основным developer entrypoint. Внутренние пути до `ops/docker/` и `migrations/alembic.ini` скрыты внутри целей.

На практике обычно достаточно:

- `make install`
- `make run`
- `make health`
- `make migrate`
- `make test`
- `make lint`
- `make docker-up`
- `make full`

Полный список:

```bash
make help
```

## Эксплуатация / диагностика

Основные точки входа:

```bash
make health
make run
make logs
docker compose -f ops/docker/compose.yml ps
```

Команда `/health` доступна операторам и суперадминистраторам и показывает:

- состояние bootstrap;
- доступность PostgreSQL;
- доступность Redis;
- готовность Telegram runtime;
- корректность Redis-backed FSM.

## Структура проекта

```text
.
├── Makefile
├── README.md
├── migrations/
│   ├── alembic.ini
│   └── versions/
├── ops/
│   ├── docker/
│   └── env/
├── src/
│   ├── app/
│   ├── application/
│   ├── bot/
│   ├── domain/
│   └── infrastructure/
└── tests/
```

## Дальнейшее развитие

Без смены текущей архитектурной линии проект безопасно расширяется в направлениях:

- SLA-автоматизация;
- более глубокая runtime-наблюдаемость;
- операционная аналитика;
- дополнительные application/use-case сценарии без размывания слоев.
