# Деплой и обновление

## Перед началом

Перед обновлением проверьте:

- `.env` соответствует окружению;
- `BOT__TOKEN` задан для режима `APP__DRY_RUN=false`;
- `BACKEND_AUTH__TOKEN` и `AI_SERVICE_AUTH__TOKEN` не пустые и совпадают между потребителями;
- `MINI_APP__PUBLIC_URL` публичный `HTTPS`, если Mini App должен открываться из Telegram;
- есть свежий backup PostgreSQL перед миграциями;
- понятно, есть ли в релизе изменения схемы базы или `.proto`.

Backup:

```bash
make backup-db
```

## Команды деплоя

Обычный Docker Compose запуск проекта:

```bash
make up
```

Полный сценарий с ожиданием готовности:

```bash
make full
```

Для production без dev overlay:

```bash
docker compose -f ops/docker/compose.yml up --build -d
```

## Проверка health

```bash
make ps
make health
```

Ожидаемо для `make health`:

- `postgres`, `redis`, `ai-service`, `backend`, `bot` в состоянии `healthy` или `running`;
- `backend` не перезапускается на миграциях;
- Mini App отвечает на `make health-mini-app` или `curl http://127.0.0.1:8088/healthz`.

## Smoke-проверка

```bash
make smoke
```

Smoke должен подтвердить:

- PostgreSQL доступен;
- Redis доступен;
- `ai-service` отвечает по gRPC;
- `backend` отвечает по gRPC;
- backend выполняет функциональный запрос;
- bot runtime diagnostics готовы.

Если smoke падает, релиз не считается принятым. Начинайте с:

```bash
make logs-backend
make logs-ai
make logs-bot
```

## Миграции

В контейнерном запуске миграции выполняет `backend` при старте (`RUN_MIGRATIONS=true`).

Локально:

```bash
make migration-check
```

В стеке:

```bash
make migrate-stack
```

Перед откатом после применённых миграций проверьте, совместим ли старый код с новой схемой. Автоматического rollback миграций в проекте нет.

## Что учитывать при откате

Откат кода допустим только после проверки:

- не применялись ли необратимые миграции;
- не изменились ли значения internal tokens;
- не поменялись ли порты и service targets;
- не появились ли новые данные, которые старый код не понимает.

Быстрый технический откат обычно выглядит как запуск предыдущего образа или предыдущей версии репозитория тем же Compose-файлом. Восстановление PostgreSQL из dump - отдельное решение, потому что оно перезаписывает данные.

## Проверки после деплоя

После принятия релиза:

```bash
make health
make smoke
make logs-backend
```

Что проверить вручную:

- клиент может создать заявку в Telegram;
- оператор видит очередь;
- Mini App открывается через кнопку `Панель`;
- заявка открывается в workspace;
- экспорт заявки скачивается;
- AI-состояние понятно: либо подсказки работают, либо UI показывает недоступность без падения.
