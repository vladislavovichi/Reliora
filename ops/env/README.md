# Переменные окружения

Источник правды для конфигурации - корневой `.env.example`.

Для локальной разработки создайте личный файл:

```bash
cp .env.example .env.local
```

`.env.local` не коммитится. Старый `.env` тоже игнорируется, но новый загрузчик
его не читает автоматически: перенесите значения в `.env.local`.

## Порядок загрузки

`Settings` в `src/infrastructure/config/settings.py` читает значения в таком
приоритете:

1. переменные окружения процесса;
2. `.env.local`, если файл существует;
3. `.env.test` только во время `pytest`, если нужен тестовый fallback.

Docker Compose и `Makefile` также используют `.env.local` как локальный env file.

## Первый запуск

```bash
cp .env.example .env.local
make full
make health
make smoke
```

Для старта без Telegram polling оставьте:

```dotenv
APP__DRY_RUN=true
```

Для реального polling задайте рабочий `TELEGRAM_BOT_TOKEN` и переключите:

```dotenv
APP__DRY_RUN=false
```

## Обязательные значения

- `AUTHORIZATION__SUPER_ADMIN_TELEGRAM_USER_IDS` - Telegram user id хотя бы одного super admin.
- `BACKEND_AUTH__TOKEN` - shared token для внутренних gRPC вызовов к backend.
- `AI_SERVICE_AUTH__TOKEN` - shared token для gRPC вызовов к ai-service.
- `TELEGRAM_BOT_TOKEN` - обязателен только когда `APP__DRY_RUN=false`.

## Основные опциональные значения

- `DATABASE_URL` или набор `DATABASE__HOST`, `DATABASE__PORT`, `DATABASE__USER`, `DATABASE__PASSWORD`, `DATABASE__DATABASE`.
- `REDIS_URL` или набор `REDIS__HOST`, `REDIS__PORT`, `REDIS__DB`, `REDIS__PASSWORD`.
- `MINI_APP__PUBLIC_URL` - нужен для Telegram Mini App button; должен быть публичным `HTTPS` URL.
- `AI__LOCAL_*` и generation limits - настройка локальной transformers-модели.
- `LOGGING__*`, `RESILIENCE__*`, `ATTACHMENTS__*`, `EXPORTS__*`, `ASSETS__PATH`.

## Docker Compose

`make full`, `make up`, `make down`, `make logs` запускают Compose через:

```text
docker compose --env-file .env.local -f ops/docker/compose.yml -f ops/docker/compose.dev.yml
```

В `.env.local` можно держать `DATABASE_URL` и `REDIS_URL` для локальных команд с
хоста. Внутри контейнеров Compose очищает эти flat URL и задаёт service names
через `DATABASE__HOST=postgres`, `REDIS__HOST=redis`, `BACKEND_SERVICE__HOST=backend`
и `AI_SERVICE__HOST=ai-service`.

Для локального публичного tunnel Mini App:

```bash
make full-cloudflared
```

Команда обновляет `MINI_APP__PUBLIC_URL` в `.env.local` и перезапускает `bot` и
`mini-app`, если они уже запущены.

## Тесты

Обычный запуск:

```bash
PYTHONPATH=src python -m pytest
```

Если нужен тестовый fallback, создайте `.env.test`. Он читается только под
`pytest` и имеет меньший приоритет, чем реальные переменные окружения и
`.env.local`.

Не добавляйте реальные токены, пароли или ключи в `.env.example` и файлы под
`ops/env/`.
