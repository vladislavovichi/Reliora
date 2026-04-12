# Reliora

`Reliora` — внутренний helpdesk в Telegram с отдельными `backend` и `ai-service` на gRPC.

Проект собран вокруг одной идеи: оператору не нужен шумный кабинет, если рабочее место уже находится там, где идёт диалог. Клиент пишет в Telegram, бот аккуратно ведёт intake, backend держит продуктовые правила, а оператор работает в спокойном кнопочном интерфейсе с архивом, аналитикой, макросами, заметками, вложениями и экспортами.

## Почему проект интересен

- Telegram остаётся основным продуктовым интерфейсом, а не временной оболочкой.
- Бизнес-логика вынесена из bot-слоя в отдельный application/backend контур.
- Исторические кейсы, аналитика и отчёты уже оформлены как самостоятельные эксплуатационные поверхности.
- Вложения, внутренние заметки, feedback и роли встроены в основную модель работы, а не добавлены поверх.
- Архитектура сохраняет явную границу `bot -> gRPC -> backend -> gRPC -> ai-service`.

## Что уже есть

- intake по темам и создание заявки из первого сообщения;
- live-диалог клиента и оператора;
- очередь, личные заявки и активный ticket context;
- архив закрытых дел с фильтрацией по темам и быстрым экспортом;
- HTML / CSV экспорт по заявке;
- HTML / CSV экспорт аналитики;
- AI assist вынесен в отдельный runtime `ai-service`: автосводка дела, подсказки по макросам и рекомендация темы intake;
- категории, метки, макросы, внутренние заметки и survey/feedback;
- роли `user`, `operator`, `super_admin`;
- one-time invite-коды для onboarding операторов;
- Redis-backed FSM, locks, presence и SLA coordination;
- отдельный gRPC backend с internal auth, audit trail и readiness checks.

## Быстрый старт

```bash
cp .env.example .env
make full
```

Для более аккуратной конфигурации можно собрать `.env` из доменных шаблонов в [ops/env/README.md](ops/env/README.md).

Для локального прогона без реального polling:

```dotenv
APP__DRY_RUN=true
```

### AI assist

Bot остаётся presentation-слоем: он не хостит модель и не знает provider-деталей. Backend решает, когда запрашивать AI, а сам inference живёт в отдельном `ai-service` за контуром `bot -> gRPC -> backend -> gRPC -> ai-service`.

Минимальный набор env:

```dotenv
AI_SERVICE__HOST=localhost
AI_SERVICE__PORT=50081
AI_SERVICE_AUTH__TOKEN=change-me-ai-in-prod

AI__PROVIDER=huggingface
AI__MODEL_ID=Qwen/Qwen3.5-4B
AI__API_TOKEN=hf_xxx
```

Этого достаточно, чтобы включить:

- автосводку заявки по полной сохранённой истории;
- подсказки по релевантным макросам внутри карточки оператора;
- рекомендацию темы при новом intake.

Полный стек в Docker Compose теперь поднимает `postgres`, `redis`, `ai-service`, `backend` и `bot`. Для локального старта пригодятся:

- `make run-ai`
- `make run-backend`
- `make run-bot`
- `make health-ai`
- `make logs-ai`

## Где читать дальше

- [Продукт и UX](docs/product/README.md)
- [Архитектура](docs/architecture/README.md)
- [Backend и gRPC](docs/backend/README.md)
- [Telegram bot](docs/bot/README.md)
- [Разработка](docs/development/README.md)
- [Эксплуатация](docs/operations/README.md)
- [Безопасность и hardening](docs/security/README.md)
