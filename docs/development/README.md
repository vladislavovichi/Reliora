# Разработка

## Базовый Локальный Цикл

```bash
cp .env.example .env
make install
make migrate
make run-ai
make run-backend
make run-bot
```

Если нужен локальный прогон без реального Telegram polling:

```dotenv
APP__DRY_RUN=true
```

## Что Считается Нормой Для Изменений

- handlers остаются тонкими;
- новые product rules идут в `application`;
- transport-изменения не смешиваются с бизнес-логикой;
- тексты живут в `bot/texts`;
- клавиатуры — в `bot/keyboards`;
- форматирование — в `bot/formatters`;
- HTML/CSV rendering — в `infrastructure/exports`;
- repository contracts меняются явно, а не побочно.

## Основные Команды

```bash
make format
make lint
make typecheck
make test
make check
```

## Что Важно Не Сломать

- реальный gRPC backend extraction;
- отдельный ai-service runtime и backend-to-ai gRPC boundary;
- роли и authorization;
- live dialogue;
- queue pagination и active ticket context;
- categories, feedback, exports и analytics;
- attachments и internal notes;
- Redis-backed FSM и runtime locks;
- premium button-first UX.

## Практический Подход

Лучший способ двигать проект дальше — улучшать продукт маленькими законченными проходами:

- одна capability;
- одна понятная архитектурная точка расширения;
- тесты рядом с изменением;
- без широких speculative refactor'ов.
