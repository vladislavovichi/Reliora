# Эксплуатация

Этот раздел нужен для запуска, проверки и разбора сбоев работающего стека.

## Компоненты

- `postgres` - основная база данных.
- `redis` - FSM, блокировки, presence, rate limits, streams, SLA runtime state.
- `ai-service` - внутренний gRPC-сервис AI-операций.
- `backend` - продуктовый gRPC-сервис.
- `bot` - Telegram runtime.
- `mini-app` - HTTP gateway и статический frontend Mini App.

## Нормальный порядок старта

1. `postgres` проходит `pg_isready`.
2. `redis` отвечает на `PING`.
3. `ai-service` поднимает gRPC endpoint.
4. `backend` применяет Alembic migrations и проверяет PostgreSQL, Redis, `ai-service`.
5. `bot` проверяет backend и runtime-зависимости.
6. `mini-app` проверяет связь с backend и отдаёт `/healthz`.

В Compose эти зависимости описаны через health checks. `backend` запускает миграции, `bot` и `mini-app` миграции не запускают.

## Проверки health

```bash
make ps
make health
make smoke
```

`make health` по умолчанию проверяет `postgres`, `redis`, `ai-service`, `backend`, `bot`. Mini App проверяйте отдельной командой ниже или через `STACK_SERVICES`.

Дополнительные проверки процессов:

```bash
make health-backend
make health-ai
make health-bot
make health-mini-app
curl http://127.0.0.1:8088/healthz
```

`make smoke` проверяет PostgreSQL, Redis, видимость AI-провайдера, gRPC `ai-service`, gRPC `backend`, функциональный backend call и bot runtime diagnostics.

## Логи

```bash
make logs
make logs-backend
make logs-ai
make logs-bot
make logs-mini-app
```

Первый лог для большинства проблем - `make logs-backend`: там видны миграции, startup checks, связь с Redis/PostgreSQL/AI и ошибки internal auth.

## Backup, деплой и диагностика

- [Деплой и обновление](runbooks/deploy.md)
- [Диагностика и типовые сбои](runbooks/diagnostics.md)
- [Backup и restore PostgreSQL](runbooks/backup-restore.md)

## Что помнить

- Redis можно восстановить как runtime-зависимость, но потерянный FSM-контекст не восстанавливается из backup.
- Backup базы не включает `ASSETS__PATH`, `.env` и Docker volumes вне PostgreSQL dump.
- Отключённый AI provider - degraded mode; недоступный `ai-service` ломает готовность backend.
- Пустой или невалидный `MINI_APP__PUBLIC_URL` отключает Telegram launch button, но не ломает bot.
