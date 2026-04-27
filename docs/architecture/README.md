# Архитектура

Документ описывает рабочие границы Reliora: какой сервис за что отвечает, как идут запросы и куда вносить изменения.

## Общая схема

```text
Telegram
  |
  v
bot --------------------.
  | gRPC                |
  v                     |
backend <--- gRPC --- mini-app HTTP gateway + static frontend
  |
  | gRPC
  v
ai-service

postgres - durable state
redis    - runtime coordination
```

## Ответственность сервисов

| Сервис | Ответственность |
| --- | --- |
| `bot` | Telegram update handling, тексты, клавиатуры, форматирование, доставка сообщений и файлов |
| `mini-app` | проверка Telegram init data, HTTP API для frontend, статические файлы Mini App |
| `backend` | бизнес-операции helpdesk, авторизация ролей, аудит, экспорт, оркестрация AI |
| `ai-service` | структурированные AI-операции: summary, reply draft, macros, category, sentiment |
| `postgres` | заявки, сообщения, операторы, инвайты, справочники, обратная связь, аудит, AI-сводки |
| `redis` | FSM, блокировки, presence, rate limits, streams, SLA runtime-состояние |

## Слои в коде

- `application` - сценарии и сервисы приложения. Здесь принимаются продуктовые решения.
- `domain` - статусы, роли, сущности, инварианты и контракты репозиториев.
- `infrastructure` - PostgreSQL, Redis, assets, exports, logging, settings, AI provider.
- Transport adapters - `src/bot`, `src/backend/grpc`, `src/mini_app`, `src/ai_service/grpc`.

Транспортные объекты не должны протекать в `application`: protobuf, aiogram `Message` и HTTP request остаются на краях системы.

## Потоки запросов

### Сообщение клиента

```text
Telegram update
-> bot handler
-> backend gRPC CreateTicketFromClientMessage/CreateTicketFromClientIntake
-> application ticket use case
-> postgres event/message/ticket rows
-> optional ai-service category/sentiment
```

Bot нормализует Telegram-ввод и вложения. Backend создаёт или обновляет заявку и пишет события.

### Действие оператора в боте

```text
callback/message
-> bot handler
-> backend gRPC
-> HelpdeskService
-> application use case
-> postgres/audit
-> bot delivery to client/operator
```

Пример: взять заявку, ответить, закрыть, добавить заметку, применить макрос.

### Действие в Mini App

```text
frontend fetch
-> mini-app HTTP
-> Telegram init data validation
-> backend gRPC with actor metadata
-> application use case
-> JSON or file response
```

Mini App не ходит в базу напрямую. Он проверяет запуск Telegram и передаёт действие в backend.

### AI-запрос

```text
backend
-> builds structured command
-> ai-service gRPC
-> provider or local sentiment logic
-> validated structured result
-> backend product response
```

`ai-service` возвращает подсказки. Решение о том, как показать их оператору, остаётся в backend и UI.

### Генерация экспорта

```text
bot or mini-app
-> backend ExportTicketReport/ExportAnalyticsSnapshot
-> application export use case
-> infrastructure renderer
-> HTML/CSV bytes
```

Рендереры лежат в `src/infrastructure/exports`.

## Границы

- `bot` не владеет продуктовыми правилами. Он показывает экран, принимает ввод и вызывает backend.
- `mini-app` не обращается к PostgreSQL или Redis напрямую.
- `backend` владеет бизнес-решениями, доступами, аудитом и контрактом данных наружу.
- `ai-service` возвращает структурированные предложения, а не меняет состояние helpdesk.
- `postgres` - источник долговременной правды.
- `redis` - координация во время работы, не архив и не backup-источник.

## Куда класть изменения

| Изменение | Директория |
| --- | --- |
| новое правило заявки | `src/application/use_cases/tickets` или `src/application/services/helpdesk` |
| новый gRPC метод backend | `src/backend/proto`, `src/backend/grpc`, `src/backend/grpc/translators*` |
| новая Telegram-кнопка или экран | `src/bot/texts`, `src/bot/keyboards`, `src/bot/formatters`, `src/bot/handlers` |
| новый экран Mini App | `src/mini_app/static/assets`, при необходимости `src/mini_app/api.py` и `src/mini_app/http.py` |
| новое поле экспорта | `src/application/use_cases/*/exports.py` и `src/infrastructure/exports` |
| новая AI-операция | `src/ai_service/proto`, `src/ai_service/service.py`, `src/application/use_cases/ai` |
| новая таблица | `src/infrastructure/db/models`, `src/infrastructure/db/repositories`, `migrations/versions` |

## Известные компромиссы

- Сервисов больше, чем в одном bot script. Это повышает стоимость локальной сборки, но отделяет Telegram UX от правил helpdesk.
- Внутренний gRPC добавляет protobuf и генерацию stubs. Зато контракт между `bot`, `mini-app`, `backend` и `ai-service` явный.
- Mini App имеет отдельный HTTP gateway. Он не самый короткий путь к данным, но сохраняет единую backend-авторизацию и аудит.
- Redis хранит runtime-состояние. После потери Redis возможна потеря FSM-контекста, но история заявок остаётся в PostgreSQL.
