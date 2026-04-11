# Эксплуатация

## Runtime Контур

- PostgreSQL — основное постоянное хранилище;
- Redis — FSM, locks, presence, streams и SLA coordination;
- backend — внутренний gRPC-сервис;
- bot — Telegram runtime поверх backend client и локального service wiring.

## Основные Команды

```bash
make docker-up
make logs
make docker-down
make health
make health-backend
make migrate
```

Полный локальный happy-path:

```bash
make full
```

## Startup И Readiness

Оба процесса стартуют fail-fast:

- сначала валидируется критичная конфигурация;
- затем выполняются ограниченные readiness-checks;
- при проблеме процесс завершается без долгого неопределённого запуска.

Критичными считаются:

- `AUTHORIZATION__SUPER_ADMIN_TELEGRAM_USER_IDS`;
- `BACKEND_AUTH__TOKEN`;
- `BOT__TOKEN`, если `APP__DRY_RUN=false`;
- доступность PostgreSQL и Redis;
- для bot runtime — доступность backend gRPC.

## Health И Диагностика

`make health` и `make health-backend` показывают:

- `liveness`;
- `readiness`;
- детализацию по dependency checks.

Команда `/health` доступна операторским ролям и помогает быстро понять, что именно сейчас не готово: база, Redis, backend auth, gRPC или сам Telegram runtime.

## Экспорты И Архив

Эксплуатационно важно помнить:

- ticket exports могут включать внутренние заметки, если это разрешено конфигурацией;
- HTML ticket export встраивает только безопасные локальные изображения;
- analytics export предназначен для локального открытия и пересылки как статический HTML;
- архивные выгрузки доступны прямо из карточки закрытого дела.

## Audit Trail

Backend пишет структурные записи по чувствительным действиям:

- workflow mutations по заявке;
- exports;
- category и macro management;
- operator role changes;
- invite generation и redemption.

Это упрощает разбор спорных кейсов и даёт базовую операционную трассировку без внешней панели.
