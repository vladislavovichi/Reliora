# Reliora

`Reliora` — внутренний helpdesk в Telegram с отдельным backend-сервисом на gRPC.

Проект собран вокруг одной идеи: оператору не нужен шумный кабинет, если рабочее место уже находится там, где идёт диалог. Клиент пишет в Telegram, бот аккуратно ведёт intake, backend держит продуктовые правила, а оператор работает в спокойном кнопочном интерфейсе с архивом, аналитикой, макросами, заметками, вложениями и экспортами.

## Почему проект интересен

- Telegram остаётся основным продуктовым интерфейсом, а не временной оболочкой.
- Бизнес-логика вынесена из bot-слоя в отдельный application/backend контур.
- Исторические кейсы, аналитика и отчёты уже оформлены как самостоятельные эксплуатационные поверхности.
- Вложения, внутренние заметки, feedback и роли встроены в основную модель работы, а не добавлены поверх.
- Архитектура сохраняет явную границу `bot -> gRPC -> backend -> application -> infrastructure`.

## Что уже есть

- intake по темам и создание заявки из первого сообщения;
- live-диалог клиента и оператора;
- очередь, личные заявки и активный ticket context;
- архив закрытых дел с фильтрацией по темам и быстрым экспортом;
- HTML / CSV экспорт по заявке;
- HTML / CSV экспорт аналитики;
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

Для локального прогона без реального polling:

```dotenv
APP__DRY_RUN=true
```

## Где читать дальше

- [Продукт и UX](docs/product/README.md)
- [Архитектура](docs/architecture/README.md)
- [Backend и gRPC](docs/backend/README.md)
- [Telegram bot](docs/bot/README.md)
- [Разработка](docs/development/README.md)
- [Эксплуатация](docs/operations/README.md)
- [Безопасность и hardening](docs/security/README.md)
