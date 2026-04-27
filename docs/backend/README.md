# Backend

`backend` - внутренний gRPC-сервис и основная точка принятия продуктовых решений. Bot и Mini App вызывают его вместо прямой работы с базой.

## Что backend владеет

- создание и чтение заявок;
- очередь, назначение, переназначение, закрытие и эскалация;
- роли, operator context и `super_admin` операции;
- темы, теги, макросы и operator invites;
- обратная связь после закрытия;
- аналитика и `HTML`/`CSV` экспорты;
- аудит чувствительных действий;
- вызовы `ai-service` и обработка недоступности AI.

## Жизненный цикл запроса

1. `src/backend/grpc/server*.py` принимает gRPC request.
2. `auth.py` проверяет internal metadata и собирает `BackendRequestContext`.
3. Translators переводят protobuf в application contracts.
4. `HelpdeskService` вызывает нужную группу операций.
5. Use case работает с репозиториями и доменными правилами.
6. Результат переводится обратно в protobuf.

Главное правило: protobuf остаётся в `src/backend/grpc`, продуктовая логика живёт в `application`.

## gRPC-граница и metadata

Backend ожидает служебные заголовки:

| Header | Назначение |
| --- | --- |
| `x-helpdesk-internal-token` | внутренний токен `BACKEND_AUTH__TOKEN` |
| `x-helpdesk-caller` | имя вызывающей стороны, обычно `telegram-bot` |
| `x-correlation-id` | correlation id для логов и аудита |
| `x-helpdesk-actor-telegram-user-id` | Telegram user id действующего пользователя |

Если token не совпадает, запрос отклоняется до входа в use case.

## Карта кода

- `src/backend/proto/helpdesk.proto` - контракт backend gRPC.
- `src/backend/grpc/server.py` и `server_*` - реализация методов.
- `src/backend/grpc/client.py` - клиент, которым пользуются bot и Mini App.
- `src/backend/grpc/translators*.py` - перевод protobuf <-> application summaries.
- `src/application/services/helpdesk` - фасад операций, authorization guard, audit.
- `src/application/use_cases/tickets` - сценарии заявок.
- `src/application/use_cases/analytics` - экспорт аналитики.
- `src/infrastructure/db/repositories` - PostgreSQL-репозитории.
- `src/infrastructure/exports` - рендереры `HTML` и `CSV`.

## Авторизация и actor context

Роль пользователя вычисляется через `AuthorizationService`: `super_admin` берётся из `AUTHORIZATION__SUPER_ADMIN_TELEGRAM_USER_IDS`, оператор - из operator repository, остальные получают `user`.

Для действий оператора backend использует actor из metadata или request. Если actor в metadata и protobuf не совпадает, запрос считается некорректным.

## AI orchestration

Backend не вызывает внешний AI API напрямую. Он:

1. собирает историю заявки, заметки, макросы или список тем;
2. строит структурированную команду;
3. вызывает `ai-service` через gRPC с `AI_SERVICE_AUTH__TOKEN`;
4. получает validated result;
5. возвращает UI понятное состояние: подсказка доступна или недоступна.

Недоступный провайдер не должен ломать основную работу с заявкой.

## Exports

Backend отдаёт:

- ticket report: `TicketReportFormat.HTML` и `TicketReportFormat.CSV`;
- analytics export: секции `overview`, `operators`, `topics`, `quality`, `sla` в `HTML` или `CSV`.

Внутренние заметки в ticket report зависят от `EXPORTS__INCLUDE_INTERNAL_NOTES_IN_TICKET_REPORTS`.

## Audit

Audit пишется через `AuditTrail` в таблицу `audit_logs`. Записи содержат action, entity type, outcome, actor id, entity id/public id, correlation id и JSON metadata.

Аудируются операции управления операторами, инвайтами, темами, макросами, заявками, тегами, обратной связью и экспортами.

## Типовые изменения

### Добавить действие по заявке

1. Добавьте use case или метод в `src/application/use_cases/tickets`.
2. Подключите его в `src/application/services/helpdesk/components.py`.
3. Добавьте метод фасада в `src/application/services/helpdesk/*_operations.py`.
4. Если действие вызывается снаружи, расширьте `helpdesk.proto`, server, client и translators.
5. Добавьте audit, если действие меняет состояние или важно для разбора инцидентов.

### Добавить поле в Mini App ticket workspace

1. Проверьте, есть ли поле в `TicketDetailsSummary`.
2. Если нет - протащите его из repository -> summary -> protobuf -> translator.
3. Добавьте сериализацию в `src/mini_app/serializers.py`.
4. Обновите renderer в `src/mini_app/static/assets/renderers.js`.

### Добавить поле в export

1. Расширьте report dataclass в `src/application/use_cases/tickets/exports.py` или analytics snapshot.
2. Передайте данные из repository/use case.
3. Обновите нужные рендереры в `src/infrastructure/exports`.
4. Добавьте тест на формат, если поле влияет на безопасность CSV/HTML.

### Добавить AI-assisted operation

1. Опишите команду и результат в application contracts.
2. Добавьте gRPC метод в `src/ai_service/proto/ai_service.proto`.
3. Реализуйте prompt/result validation в `src/ai_service`.
4. Добавьте backend orchestration и degradation path.
5. Обновите UI только после появления устойчивого backend-контракта.

## Проверки

Для backend-изменений обычно нужны:

```bash
make lint
make typecheck
make test
make proto-check
make migration-check
```

Если менялись только тексты UI без backend-контракта, `proto-check` не обязателен. Если менялись модели или репозитории, `migration-check` обязателен.
