# Backend И gRPC

## Роль Backend-Слоя

Backend в Reliora — это не вспомогательный proxy для Telegram-бота, а отдельный продуктовый слой. Он принимает transport-запросы, валидирует internal metadata, вызывает use case'ы и возвращает уже собранный результат в protobuf-форме. Для AI backend теперь оркестрирует отдельный `ai-service`, а не хостит provider прямо у себя в процессе.

Основные точки входа находятся в:

- `src/backend/proto` — protobuf-контракты;
- `src/backend/grpc` — client, server, auth, translators;
- `src/backend/main.py` — runtime backend-процесса;
- `src/application/services/helpdesk` — композиция продуктовых операций.
- `src/ai_service/grpc/client.py` — backend-side transport к inference runtime.

## Что Идёт Через Backend

- создание заявки из клиентского сообщения;
- ticket details, очередь и личные заявки оператора;
- архив закрытых дел;
- reply / close / assign / macros / notes / tags;
- exports по заявке;
- analytics snapshot и analytics export.

Admin management сейчас остаётся в том же service-контуре, но invite-code onboarding и operator lifecycle всё равно живут ниже presentation-слоя.

## Transport Boundary

Backend строится вокруг явного gRPC boundary:

1. server принимает request и metadata;
2. translator собирает application-compatible payload;
3. `HelpdeskService` вызывает соответствующий use case;
4. результат сериализуется обратно в protobuf response или stream item.

Такой контур делает важную вещь: transport можно менять или расширять, не втаскивая protobuf и aiogram во внутреннюю бизнес-логику.

Для AI действует тот же принцип, но уже на втором internal hop:

1. backend собирает business-shaped request;
2. backend gRPC client обращается к `ai-service`;
3. `ai-service` делает inference и возвращает структурированный ответ;
4. backend решает, как встроить результат в продуктовый workflow.

## Internal Auth И Trace

Внутренний gRPC трафик сопровождается служебными metadata:

- `x-helpdesk-internal-token`;
- `x-helpdesk-caller`;
- `x-correlation-id`;
- `x-helpdesk-actor-telegram-user-id` там, где нужен audit context.

Для `backend -> ai-service` используется тот же стиль metadata, но с отдельным `AI_SERVICE_AUTH__TOKEN`.

Backend проверяет auth до входа в бизнес-операции. Неавторизованный вызов не должен доходить до application use case'ов.

## Audit И Эксплуатация

Backend пишет структурные audit-записи по чувствительным действиям, включая:

- ticket assign / close / reply / export;
- analytics export;
- operator promote / revoke / invite generation / invite redemption;
- category и macro management;
- feedback mutations, когда они действительно зафиксированы.

Это делает backend не только transport-слоем, но и надёжной операционной опорой проекта.
