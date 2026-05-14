# Reliora

Reliora - helpdesk в Telegram: клиент пишет в бот, оператор работает в Mini App, backend хранит процесс и историю.

## Что делает Reliora

Reliora закрывает базовый контур поддержки внутри Telegram:

- принимает обращения клиентов и сохраняет историю переписки;
- ведёт очередь заявок и личный список оператора;
- даёт оператору рабочее место в Telegram Mini App;
- хранит архив закрытых заявок;
- показывает операционную аналитику;
- отдаёт `HTML` и `CSV` выгрузки по заявкам и аналитике;
- помогает оператору через AI: сводка, черновик ответа, подсказки макросов, рекомендация темы;
- поддерживает роли `user`, `operator`, `super_admin` и одноразовые инвайты операторов.

## Схема системы

```text
bot      -> gRPC -> backend -> gRPC    -> ai-service
mini-app -> HTTP -> gRPC    -> backend -> gRPC -> ai-service
```

- `bot` - Telegram-интерфейс: команды, тексты, клавиатуры, доставка сообщений и вложений.
- `mini-app` - HTTP gateway и статический frontend для операторского рабочего места.
- `backend` - внутренний gRPC-сервис с правилами helpdesk, доступами, аудитом и экспортами.
- `ai-service` - отдельный gRPC-сервис для AI-операций.
- `postgres` - долговременное состояние: заявки, сообщения, операторы, справочники, аудит.
- `redis` - runtime-состояние: FSM, блокировки, presence, rate limits, SLA-координация.

## Быстрый старт

```bash
cp .env.example .env.local
make full
make health
make smoke
```

`make full` собирает Docker-образы, поднимает стек и ждёт готовности служб. Если нужно только поднять Compose-стек без полного сценария проверки, используйте:

```bash
make up
```

Для локального старта без реального Telegram polling оставьте:

```dotenv
APP__DRY_RUN=true
```

В этом режиме бот и зависимости инициализируются, но polling Telegram не запускается. Для настоящего бота нужен рабочий `TELEGRAM_BOT_TOKEN` и `APP__DRY_RUN=false`.

## Telegram Mini App

Кнопка меню `Панель` появляется только при валидном:

```dotenv
MINI_APP__PUBLIC_URL=https://mini-app.example.com
```

Telegram требует публичный `HTTPS` URL. Не подходят `localhost`, приватные IP, локальные домены и `http://`.

Для локальной проверки с временным публичным адресом есть сценарий через `cloudflared`:

```bash
make full-cloudflared
```

Команда поднимает стек, открывает tunnel к Mini App, обновляет `MINI_APP__PUBLIC_URL` в `.env.local` и перезапускает потребителей URL.

## AI

AI-контур работает через `ai-service`. Минимальный набор:

```dotenv
AI_SERVICE_AUTH__TOKEN=change-me-ai-in-prod
AI__MODEL_ID=Qwen/Qwen2.5-0.5B-Instruct
AI__LOCAL_MODEL_PATH=
AI__LOCAL_DEVICE=auto
AI__REPLY_DRAFT_TEMPERATURE=0.4
AI__REPLY_DRAFT_MAX_OUTPUT_TOKENS=1000
```

AI runtime локальный: `ai-service` загружает transformers model один раз при старте. Первый запуск может скачать веса в cache volumes. CPU работает по умолчанию, но может быть медленным; для локального каталога модели используйте `AI__LOCAL_MODEL_PATH=/models/<dir>`.

Для проверки статуса без генерации используйте `make health-ai`. Для реальной генерации и JSON/schema validation используйте `make ai-smoke`.

## Полезные команды

| Команда | Назначение |
| --- | --- |
| `make full` | собрать, запустить и проверить полный Docker-стек |
| `make up` / `make down` | поднять или остановить Compose-стек |
| `make ps` | показать состояние сервисов |
| `make health` | проверить health контейнеров |
| `make smoke` | проверить связи PostgreSQL, Redis, backend, ai-service и bot runtime |
| `make ai-smoke` | проверить реальный AI completion через ai-service gRPC |
| `make logs` | смотреть логи `ai-service`, `backend`, `bot`, `mini-app` |
| `make run-mini-app` | запустить Mini App gateway локально |
| `make backup-db` | создать логический backup PostgreSQL |
| `make check` | `lint`, `typecheck`, `test` |
| `make ci` | `check`, `proto-check`, `migration-check` |

Для прямого запуска Python ops-команд есть единый CLI:

```bash
PYTHONPATH=src poetry run python -m ops.cli --help
```

## Карта документации

- [Продукт](docs/product/README.md) - роли, жизненный цикл заявки, операторские поверхности и ограничения.
- [Архитектура](docs/architecture/README.md) - границы сервисов, потоки запросов и куда класть изменения.
- [Backend](docs/backend/README.md) - gRPC-граница, actor context, оркестрация AI, экспорт и аудит.
- [Bot](docs/bot/README.md) - Telegram UX, handlers, тексты, клавиатуры и вложения.
- [Mini App](docs/mini-app/README.md) - маршруты, Telegram init data, файлы frontend и типовые сбои.
- [AI](docs/ai/README.md) - AI-возможности, настройки провайдера, деградация и правила безопасности.
- [Exports](docs/exports/README.md) - состав `HTML` и `CSV` выгрузок и код рендереров.
- [Разработка](docs/development/README.md) - локальный запуск, проверки, миграции, proto и рабочие сценарии.
- [Эксплуатация](docs/operations/README.md) - порядок старта, health checks, логи, backup и runbooks.
- [Переменные окружения](ops/env/README.md) - `.env.example`, `.env.local`, минимальные настройки и частые ошибки.
- [Безопасность](docs/security/README.md) - threat model, internal auth, инвайты, вложения, экспорты и AI-граница.
