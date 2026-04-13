# Reliora

`Reliora` — внутренний helpdesk в Telegram. Клиент пишет в чат, оператор работает там же.

## Что внутри

Контур состоит из пяти служб:

- `bot` — Telegram-слой: тексты, клавиатуры, маршрутизация, доставка сообщений;
- `backend` — внутренний gRPC-сервис с продуктовой логикой;
- `ai-service` — отдельная служба для AI-задач;
- `postgres` — основное хранилище;
- `redis` — состояние диалогов, блокировки, presence, потоки и координация SLA.

Граница остаётся прямой и читаемой:

```text
bot -> gRPC -> backend -> gRPC -> ai-service
```

## Что уже есть

- приём обращения с выбором темы;
- живой диалог клиента и оператора;
- очередь, личные заявки и активный контекст оператора;
- архив закрытых дел;
- HTML- и CSV-экспорт по заявке;
- HTML- и CSV-экспорт аналитики;
- роли `user`, `operator`, `super_admin`;
- одноразовые инвайт-коды для операторов;
- вложения, внутренние заметки, теги, макросы, обратная связь;
- Redis-backed FSM и отдельный gRPC `backend`;
- AI-помощь через `ai-service`: сводка по делу, подсказки по макросам и рекомендация темы.

## Быстрый старт

```bash
cp .env.example .env
make full
```

Если нужен локальный запуск без реального polling Telegram, оставьте в `.env`:

```dotenv
APP__DRY_RUN=true
```

Для более аккуратной сборки окружения можно брать значения из шаблонов в [ops/env/README.md](ops/env/README.md).

## AI-контур

Минимально для AI нужны:

```dotenv
AI_SERVICE__HOST=localhost
AI_SERVICE__PORT=50081
AI_SERVICE_AUTH__TOKEN=change-me-ai-in-prod

AI__PROVIDER=huggingface
AI__MODEL_ID=Qwen/Qwen3.5-4B
AI__API_TOKEN=hf_xxx
```

## Основные команды

- `make up` — поднять стек в Docker Compose;
- `make health` — посмотреть состояние контейнеров;
- `make smoke` — прогнать прикладную smoke проверку;
- `make logs` — смотреть логи `ai-service`, `backend` и `bot`;
- `make backup-db` — сделать логическую резервную копию PostgreSQL.

## Документация

- [Продукт](docs/product/README.md)
- [Архитектура](docs/architecture/README.md)
- [Backend](docs/backend/README.md)
- [Bot](docs/bot/README.md)
- [Разработка](docs/development/README.md)
- [Эксплуатация](docs/operations/README.md)
- [Безопасность](docs/security/README.md)
