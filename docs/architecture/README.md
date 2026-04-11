# Архитектура Reliora

## Общая Картина

Reliora разделяет Telegram presentation и продуктовый backend настолько явно, насколько это разумно для helpdesk-продукта без web-dashboard.

Базовый маршрут данных:

```text
Telegram bot -> gRPC client -> backend service -> application use cases -> repositories -> infrastructure
```

Это не декоративная схема. Она определяет, где именно живут решения:

- `src/bot` — экраны, тексты, клавиатуры, форматирование и реакция на update;
- `src/backend` — protobuf, gRPC server/client и transport boundary;
- `src/application` — продуктовые сценарии, orchestration и бизнес-правила;
- `src/domain` — сущности, инварианты и repository contracts;
- `src/infrastructure` — PostgreSQL, Redis, exports, assets, config, logging;
- `src/app` — wiring Telegram runtime и bootstrap.

## Что Здесь Считается Важным

- Handler'ы остаются тонкими и не принимают продуктовых решений.
- Telegram-специфика не должна протекать в application use case'ы без необходимости.
- Экспорты рендерятся отдельными модулями и не смешиваются с transport-кодом.
- Архив, аналитика и onboarding операторов оформляются как backend/application capabilities, а не как набор callback-трюков.
- PostgreSQL остаётся source of truth; Redis отвечает за runtime coordination.

## Текущие Границы Ответственности

### Bot

Bot-слой отвечает за то, как продукт ощущается:

- русскоязычный интерфейс;
- кнопочная навигация;
- спокойные empty/error/confirmation states;
- live delivery клиенту и оператору;
- стартовые потоки, включая invite-code onboarding.

### Backend

Backend принимает transport request, переводит их в application-модель и возвращает уже собранный результат. Именно здесь держатся:

- ticket workflows;
- archive browsing data;
- exports;
- analytics snapshot;
- role mutations и invite-code lifecycle.

### Application

Именно application-слой должен знать:

- что считать валидным workflow;
- как обрабатывать архив и фильтры;
- как выдавать и погашать invite-коды;
- какие события и audit-записи сопровождать продуктовые действия.

## Почему Такая Схема Нужна

Telegram-интерфейс у проекта намеренно богатый: очередь, active context, архив, analytics, exports, notes, attachments, macros, tags. Без явной backend extraction всё это быстро превращается в плотный слой handler'ов с неясными границами. Текущая схема удерживает проект управляемым: UI можно полировать отдельно, а бизнес-поведение — проверять на application и repository уровне.
