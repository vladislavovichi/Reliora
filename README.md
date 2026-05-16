# Reliora

Helpdesk внутри Telegram. Клиент пишет в бот — оператор отвечает из Mini App.

## Возможности

- Приём обращений, история переписки, архив закрытых заявок
- Очередь заявок и личный список оператора
- Операторское рабочее место в Telegram Mini App
- Операционная аналитика, выгрузки `HTML` и `CSV`
- AI-ассистент: сводка, черновик ответа, подсказки макросов, рекомендация темы
- Роли `user`, `operator`, `super_admin`; одноразовые инвайты операторов

## Архитектура

```text
bot      ──gRPC──► backend ──gRPC──► ai-service
mini-app ──HTTP──► backend ──gRPC──► ai-service
                      │
                 postgres / redis
```

| Компонент | Назначение |
| --- | --- |
| `bot` | Telegram-интерфейс: команды, тексты, клавиатуры, вложения |
| `mini-app` | HTTP-gateway и статический frontend операторского рабочего места |
| `backend` | gRPC-сервис: правила helpdesk, доступы, аудит, экспорты |
| `ai-service` | gRPC-сервис AI-операций |
| `postgres` | Долговременное состояние: заявки, сообщения, операторы, аудит |
| `redis` | Runtime-состояние: FSM, блокировки, presence, rate limits, SLA |

## Быстрый старт

```bash
cp .env.example .env.local
make full
make health
make smoke
```

`make full` собирает образы, поднимает стек и ожидает готовности служб. Чтобы только поднять Compose без проверок:

```bash
make up
```

Для запуска без реального Telegram polling установите `APP__DRY_RUN=true` — бот инициализируется, но polling не стартует. Для полноценной работы нужен `TELEGRAM_BOT_TOKEN` и `APP__DRY_RUN=false`.

## Telegram Mini App

Кнопка **Панель** в меню бота появляется только при корректном публичном HTTPS-адресе:

```dotenv
MINI_APP__PUBLIC_URL=https://mini-app.example.com
```

Для локальной проверки с временным публичным адресом через `cloudflared`:

```bash
make full-cloudflared
```

Команда поднимает стек, открывает туннель к Mini App, обновляет `MINI_APP__PUBLIC_URL` в `.env.local` и перезапускает потребителей URL.

## AI

`ai-service` загружает transformers-модель при старте. Минимальная конфигурация:

```dotenv
AI_SERVICE_AUTH__TOKEN=change-me-ai-in-prod
AI__MODEL_ID=Qwen/Qwen2.5-0.5B-Instruct
AI__LOCAL_MODEL_PATH=
AI__LOCAL_DEVICE=auto
AI__REPLY_DRAFT_TEMPERATURE=0.4
AI__REPLY_DRAFT_MAX_OUTPUT_TOKENS=1000
```

По умолчанию используется CPU. Для локального каталога модели — `AI__LOCAL_MODEL_PATH=/models/<dir>`. Первый запуск может скачать веса в cache volumes.

Проверить статус без генерации: `make health-ai`. Проверить реальную генерацию: `make ai-smoke`.

## Команды

| Команда | Назначение |
| --- | --- |
| `make full` | Собрать, запустить и проверить полный Docker-стек |
| `make up` / `down` | Поднять или остановить Compose-стек |
| `make ps` | Состояние сервисов |
| `make health` | Health check контейнеров |
| `make smoke` | Проверить связи PostgreSQL, Redis, backend, ai-service, bot |
| `make ai-smoke` | Проверить AI completion через ai-service gRPC |
| `make logs` | Логи `ai-service`, `backend`, `bot`, `mini-app` |
| `make run-mini-app` | Запустить Mini App gateway локально |
| `make backup-db` | Логический backup PostgreSQL |
| `make check` | `lint`, `typecheck`, `test` |
| `make ci` | `check`, `proto-check`, `migration-check` |

Прямой запуск ops-команд:

```bash
PYTHONPATH=src poetry run python -m ops.cli --help
```

## Документация

- [Продукт](docs/product/README.md) — роли, жизненный цикл заявки, операторские поверхности
- [Архитектура](docs/architecture/README.md) — границы сервисов, потоки запросов
- [Backend](docs/backend/README.md) — gRPC-граница, actor context, AI-оркестрация, экспорт, аудит
- [Bot](docs/bot/README.md) — Telegram UX, handlers, тексты, клавиатуры, вложения
- [Mini App](docs/mini-app/README.md) — маршруты, Telegram init data, frontend, типовые сбои
- [AI](docs/ai/README.md) — возможности, настройки провайдера, деградация, правила безопасности
- [Exports](docs/exports/README.md) — состав `HTML` и `CSV` выгрузок, рендереры
- [Разработка](docs/development/README.md) — локальный запуск, проверки, миграции, proto
- [Эксплуатация](docs/operations/README.md) — порядок старта, health checks, логи, backup, runbooks
- [Переменные окружения](ops/env/README.md) — `.env.example`, `.env.local`, минимум, частые ошибки
- [Безопасность](docs/security/README.md) — threat model, internal auth, инвайты, вложения, AI-граница
