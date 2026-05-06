# Диагностика

## Начните отсюда

```bash
make ps
make health
make smoke
make logs-backend
```

Если проблема явно в UI, добавьте:

```bash
make logs-bot
make logs-mini-app
curl http://127.0.0.1:8088/healthz
```

## Backend недоступен

Команды:

```bash
make logs-backend
make health-backend
```

Вероятные причины:

- PostgreSQL недоступен или неверные `DATABASE__*`;
- Redis недоступен или неверные `REDIS__*`;
- `ai-service` не отвечает по `AI_SERVICE__HOST`/`AI_SERVICE__PORT`;
- не совпадает `AI_SERVICE_AUTH__TOKEN`;
- Alembic migration завершилась ошибкой.

Следующие проверки:

```bash
make logs-ai
make ps
make migration-check
```

## AI-service недоступен

Команды:

```bash
make logs-ai
make health-ai
```

Разделяйте два случая:

- `ai-service` жив, но локальная модель не загрузилась - backend не должен считать AI готовым;
- `ai-service` не отвечает по gRPC - backend не проходит готовность.

Проверьте:

- `AI_SERVICE__HOST`;
- `AI_SERVICE__PORT`;
- `AI_SERVICE_AUTH__TOKEN`;
- `AI__MODEL_ID`;
- `AI__LOCAL_MODEL_PATH`;
- `AI__LOCAL_DEVICE`;
- `AI__LOCAL_DTYPE`.

Для локальной модели проверьте:

- `make health-ai`;
- `docker compose -f ops/docker/compose.yml -f ops/docker/compose.dev.yml ps ai-service`;
- `AI__MODEL_ID` или `AI__LOCAL_MODEL_PATH`;
- cache volumes `ai-huggingface-cache`, `ai-torch-cache`, `ai-torch-kernels-cache`;
- `make ai-smoke`.

## Bot недоступен

Команды:

```bash
make logs-bot
make health-bot
```

Вероятные причины:

- `APP__DRY_RUN=false`, но `TELEGRAM_BOT_TOKEN` пустой или неверный;
- backend недоступен;
- Redis/PostgreSQL недоступны для runtime diagnostics;
- Telegram polling конфликтует с другим запущенным экземпляром бота.

Если нужен локальный режим без polling:

```dotenv
APP__DRY_RUN=true
```

## Mini App недоступен

Команды:

```bash
make logs-mini-app
make health-mini-app
curl http://127.0.0.1:8088/healthz
```

Вероятные причины:

- `mini-app` не может дойти до backend;
- внешний порт отличается от ожидаемого `MINI_APP_EXPOSE_PORT`;
- `MINI_APP__PUBLIC_URL` невалиден для Telegram launch;
- frontend открыт не из Telegram и init data отсутствует.

Важно: `/healthz` может отвечать локально, даже если Telegram launch button не работает из-за публичного URL.

## Проблема PostgreSQL

Признаки:

- `backend` падает на startup check `postgresql`;
- `make smoke` падает на проверке базы;
- в логах есть connection refused, timeout или SQLAlchemy exception.

Проверьте:

```bash
make ps
make logs-backend
docker compose -f ops/docker/compose.yml -f ops/docker/compose.dev.yml logs postgres
```

Параметры:

- `DATABASE__HOST`;
- `DATABASE__PORT`;
- `DATABASE__USER`;
- `DATABASE__PASSWORD`;
- `DATABASE__DATABASE`;
- `POSTGRES_EXPOSE_PORT`.

## Проблема Redis

Признаки:

- bot или backend падает на startup check `redis`;
- теряется FSM-контекст;
- operator presence или блокировки работают нестабильно.

Проверьте:

```bash
make ps
make logs-backend
make logs-bot
docker compose -f ops/docker/compose.yml -f ops/docker/compose.dev.yml logs redis
```

Параметры:

- `REDIS__HOST`;
- `REDIS__PORT`;
- `REDIS__DB`;
- `REDIS__PASSWORD`;
- `REDIS_EXPOSE_PORT`.

После восстановления Redis прогоните:

```bash
make health
make smoke
```

## Mini App button missing

Проверьте:

```bash
make logs-bot
make logs-mini-app
make health-bot
curl http://127.0.0.1:8088/healthz
```

Частые причины:

- `MINI_APP__PUBLIC_URL` пустой;
- URL начинается с `http://`;
- указан `localhost`, приватный IP или локальный домен;
- после изменения `.env.local` не перезапущены `bot` и `mini-app`;
- `cloudflared` tunnel сменил адрес, а `.env.local` ещё содержит старый.

Для временного публичного URL:

```bash
make full-cloudflared
```

## AI настроен, но не работает

Команды:

```bash
make logs-ai
make logs-backend
make smoke
```

Проверьте:

- `AI__MODEL_ID` задан;
- `AI__LOCAL_MODEL_PATH` существует, если задан;
- cache volumes доступны на запись;
- хватает памяти под модель;
- `AI_SERVICE_AUTH__TOKEN` одинаковый для backend и `ai-service`;
- runtime AI settings в Mini App admin не отключают нужную функцию.

Если локальная модель возвращает ошибку, `ai-service` должен показать короткую sanitized причину, а UI - недоступность конкретной подсказки.

## Экспорты падают

Команды:

```bash
make logs-backend
make smoke
```

Проверьте:

- существует ли заявка;
- есть ли доступ у actor;
- корректен ли `format`: `html` или `csv`;
- для analytics корректны `section` и `window`;
- не ломает ли новое поле renderer в `src/infrastructure/exports`.

Если экспорт падает только в Mini App, дополнительно смотрите:

```bash
make logs-mini-app
```

## Классификация startup checks

В логах startup checks используются категории:

- `auth_issue` - internal token или actor metadata;
- `config_issue` - неполная или неверная конфигурация;
- `dependency_issue` - сеть, порт, контейнер или внешний сервис;
- `runtime_issue` - ошибка внутри процесса после чтения конфигурации.
