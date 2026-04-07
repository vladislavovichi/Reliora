# Reliora

`Reliora` — Telegram helpdesk-сервис для приема клиентских обращений, обработки очереди заявок операторами и управления ролями внутри одного бота.

## Что умеет проект

- принимает сообщения клиентов и создает заявки;
- продолжает переписку в уже открытой заявке;
- дает операторам очередь, карточки заявок, ответы, эскалацию, переназначение, макросы, теги и статистику;
- дает супер администраторам управление операторами;
- хранит состояние в PostgreSQL и Redis;
- использует Redis-backed FSM для состояний `aiogram`.

## Архитектура

Проект использует `src/` layout и явные слои:

```text
src/
  app/             bootstrap, runtime, entrypoint
  application/     use cases и orchestration сервисов
  bot/             handlers, middlewares, texts, keyboards, formatters
  domain/          сущности, enum'ы, бизнес-правила, контракты репозиториев
  infrastructure/  config, PostgreSQL, Redis, logging
tests/             тесты
migrations/        Alembic
```

Основной поток:

1. Telegram update попадает в `bot`.
2. Handler вызывает `application`-сервис.
3. Сервис использует конкретные use case'ы и доменные правила.
4. Репозитории и Redis-адаптеры из `infrastructure` сохраняют состояние и выполняют технические операции.

Слои не должны обходить друг друга: `bot -> application -> domain/contracts -> infrastructure`.

## Роли и доступ

Поддерживаются три роли:

- пользователь: может писать в бот и продолжать свои обращения;
- оператор: может работать с очередью, заявками, макросами, тегами и статистикой;
- супер администратор: имеет все права оператора и дополнительно управляет операторами.

Супер администраторы задаются списком Telegram ID через `.env`:

```dotenv
AUTHORIZATION__SUPER_ADMIN_TELEGRAM_USER_IDS=12345,67890,11111
```

Правила:

- пустые элементы игнорируются;
- значения должны быть положительными целыми числами;
- роль оператора продолжает определяться через таблицу операторов;
- супер администраторы не требуют отдельной записи в таблице операторов.

Команды супер администратора:

- `/operators`
- `/add_operator <telegram_user_id> [display_name]`
- `/remove_operator <telegram_user_id>`

## Конфигурация

Настройки читаются через `pydantic-settings` с группами:

- `app`
- `bot`
- `authorization`
- `database`
- `redis`
- `logging`

Основные переменные:

```dotenv
APP__NAME=tg-helpdesk
APP__ENVIRONMENT=dev
APP__DRY_RUN=true

BOT__TOKEN=

AUTHORIZATION__SUPER_ADMIN_TELEGRAM_USER_IDS=123456789,987654321

DATABASE__URL=
DATABASE__HOST=postgres
DATABASE__PORT=5432
DATABASE__USER=helpdesk
DATABASE__PASSWORD=helpdesk
DATABASE__DATABASE=helpdesk
DATABASE__ECHO=false

REDIS__URL=
REDIS__HOST=redis
REDIS__PORT=6379
REDIS__DB=0
REDIS__PASSWORD=

LOGGING__LEVEL=INFO
LOGGING__STRUCTURED=true
```

Дополнительно для локального Docker:

- `POSTGRES_EXPOSE_PORT`
- `REDIS_EXPOSE_PORT`

## Локальный запуск

Требования:

- Python 3.12+
- Poetry
- PostgreSQL и Redis, либо Docker Compose
- корректный список `AUTHORIZATION__SUPER_ADMIN_TELEGRAM_USER_IDS`
- `BOT__TOKEN`, если `APP__DRY_RUN=false`

Подготовка:

```bash
cp .env.example .env
make install
```

Применить миграции:

```bash
make migrate
```

Проверить готовность зависимостей и runtime wiring:

```bash
make health
```

Запустить приложение локально:

```bash
make run
```

Фактический entrypoint:

```bash
PYTHONPATH=src poetry run python -m app.main
```

Поведение старта:

- приложение централизованно проверяет конфигурацию, PostgreSQL и Redis до запуска polling;
- при ошибке зависимости startup завершается сразу с понятной записью в логах;
- если `APP__DRY_RUN=true`, инфраструктура поднимется, но polling Telegram не запустится;
- для реальной работы задайте `BOT__TOKEN` и `APP__DRY_RUN=false`.

Проверка из Telegram:

- команда `/health` доступна операторам и супер администраторам;
- команда показывает состояние bootstrap, PostgreSQL, Redis и Telegram runtime.

## Docker

Полный happy-path запуск с проверкой health:

```bash
make full
```

`make full`:

- собирает и поднимает весь Docker Compose stack в фоне;
- ждет healthcheck'и `postgres`, `redis` и `app` с bounded timeout;
- считает запуск успешным только если `app` становится `healthy`;
- при сбое печатает `docker compose ps` и релевантные логи, в первую очередь `app`.

Базовый запуск без ожидания health:

```bash
make docker-up
```

Посмотреть логи приложения:

```bash
make logs
```

Проверить локальный healthcheck контейнера:

```bash
docker compose ps
```

Остановить стек:

```bash
make docker-down
```

Альтернатива с тем же эффектом:

```bash
make full-down
```

Сервисы в Compose:

- `app`
- `postgres`
- `redis`

Контейнер `app`:

- ждет `postgres` и `redis` по healthcheck;
- автоматически применяет миграции через `alembic upgrade head` в startup flow контейнера;
- запускает приложение;
- публикует собственный healthcheck через `python -m app.healthcheck`.

Для ручной инспекции:

- `make logs` показывает live-логи `app`;
- `docker compose logs -f postgres redis app` показывает логи всего стека;
- `docker compose ps` показывает текущее состояние и health сервисов.

## Redis и FSM

Redis используется для:

- FSM storage `aiogram`;
- rate limiting;
- locks по заявкам;
- presence операторов;
- stream/publish событий;
- SLA deadline scheduling.

FSM больше не использует `MemoryStorage`: runtime создает `RedisStorage` поверх общего Redis-клиента приложения.

## Миграции

Применить все миграции:

```bash
make migrate
```

Создать новую миграцию:

```bash
make make-migration name=add_some_table
```

Прямые команды Alembic:

```bash
poetry run alembic current
poetry run alembic history
poetry run alembic upgrade head
```

Проверить, что новых автогенерируемых миграций нет:

```bash
make migration-check
```

## Проверки качества и разработка

Форматирование:

```bash
make format
```

Линтинг и типы:

```bash
make lint
```

Тесты:

```bash
make test
```

Полный локальный прогон:

```bash
make check
```

Локальный прогон CI-проверок с проверкой согласованности миграций:

```bash
make ci
```

В GitHub Actions используются те же команды: `make lint`, `make test`, `make migration-check`.

Pre-commit:

```bash
make pre-commit-install
make pre-commit-run
```

## Эксплуатация и диагностика

Основные операционные команды:

```bash
make health
make run
make docker-up
make logs
make docker-down
```

`make health` поднимает тот же bootstrap-контур без polling и проверяет:

- конфигурацию запуска;
- доступность PostgreSQL;
- доступность Redis;
- готовность Telegram runtime и Redis-backed FSM.

Graceful shutdown:

- при остановке приложения закрывается Telegram session;
- закрывается FSM storage;
- закрывается Redis client;
- SQLAlchemy engine корректно dispose'ится;
- ошибки закрытия логируются отдельно и не маскируют остальные cleanup-шаги.

Типовые проблемы запуска:

- `BOT__TOKEN не задан`: установите `BOT__TOKEN` или включите `APP__DRY_RUN=true`.
- ошибка PostgreSQL readiness: проверьте `DATABASE__*`, доступность БД и примените `make migrate`.
- ошибка Redis readiness: проверьте `REDIS__*` и доступность Redis.
- приложение стартует, но polling не идет: проверьте, что `APP__DRY_RUN=false`.
