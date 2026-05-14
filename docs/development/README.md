# Разработка

Этот документ для ежедневной работы с репозиторием: поднять окружение, внести изменение, прогнать проверки и не сломать границы сервисов.

## Требования

- Python `3.12`;
- Poetry;
- Docker и Docker Compose;
- `make`;
- для локального Mini App tunnel - `cloudflared` или бинарь `/tmp/cloudflared`.

Зависимости описаны в `pyproject.toml`.

## Локальная настройка

```bash
cp .env.example .env.local
poetry env use python3.12
make install
```

Для локального режима без Telegram polling оставьте:

```dotenv
APP__DRY_RUN=true
```

## Запуск сервисов локально

Локальные команды запускают процессы через Poetry:

```bash
make run-backend
make run-ai
make run-bot
make run-mini-app
```

Обычно удобнее поднимать весь стек в Docker, а локально запускать только тот процесс, который сейчас меняется.

## Docker

```bash
make up
make ps
make health
make smoke
```

`make up` использует `ops/docker/compose.yml` и `ops/docker/compose.dev.yml`. Dev-файл монтирует репозиторий в контейнеры `ai-service`, `backend`, `bot`.

Полный сценарий:

```bash
make full
```

Остановка:

```bash
make down
```

## Mini App локально

Mini App gateway запускает FastAPI ASGI app через Uvicorn и слушает `MINI_APP__LISTEN_HOST` и `MINI_APP__PORT`. В Docker наружный порт задаётся `MINI_APP_EXPOSE_PORT`, по умолчанию `8088`.

Проверка endpoint:

```bash
curl http://127.0.0.1:8088/healthz
```

Для запуска из Telegram нужен публичный `HTTPS` URL:

```bash
make full-cloudflared
```

Команда обновит `MINI_APP__PUBLIC_URL` в `.env.local`. После ручного изменения этого URL перезапустите `bot` и `mini-app`, чтобы кнопка меню и health checks увидели новое значение.

## AI локально

Reliora использует только локальную transformers-модель внутри `ai-service`:

```bash
make docker-up
make health-ai
make ai-smoke
```

Модель загружается один раз при старте `ai-service`. По умолчанию используется `Qwen/Qwen2.5-0.5B-Instruct`. Для локального каталога модели положите его в `models/` и задайте `AI__LOCAL_MODEL_PATH=/models/qwen`.

`make health-ai` проверяет статус без генерации. `make ai-smoke` выполняет реальную генерацию и JSON/schema validation.

Для запуска `ai-service` без Docker установите локальную AI-группу зависимостей:

```bash
poetry install --with local-ai
make run-ai
```

## Проверки

| Команда | Что проверяет |
| --- | --- |
| `make format` | Ruff autofix и форматирование |
| `make lint` | Ruff без изменений |
| `make typecheck` | mypy по `src` и `tests` |
| `make test` | pytest |
| `make test-unit` | чистые unit-тесты без реальных runtime-границ |
| `make test-component` | component-тесты с fake/stub/mock зависимостями |
| `make test-integration` | integration-тесты через реальные API/infra границы |
| `make proto-check` | gRPC stubs соответствуют `.proto` |
| `make migration-check` | Alembic upgrade и `alembic check` |
| `make smoke` | работающий стек и ключевые связи |
| `make health-ai` | статус локальной модели без генерации |
| `make ai-smoke` | реальная AI-проверка через локальную модель |
| `make check` | `lint`, `typecheck`, `test` |
| `make ci` | `check`, `proto-check`, `migration-check` |

Нетривиальные Python-проверки также собраны в ops CLI. Makefile остаётся основным интерфейсом, а для прямого запуска используйте:

```bash
PYTHONPATH=src poetry run python -m ops.cli --help
PYTHONPATH=src poetry run python -m ops.cli port-available 8088
```

Тесты разложены по таксономии:

- `tests/unit` — чистые unit-тесты, без реальных API/infra границ.
- `tests/component` — handlers/services/repositories/gateways с fake, stub или mock зависимостями. Эти тесты должны запускаться без PostgreSQL, Redis, Telegram Bot API и других внешних сервисов.
- `tests/integration` — только реальные границы: живой gRPC/HTTP сервер и клиент, PostgreSQL, Redis или аналогичная инфраструктура.
- `tests/e2e` — полный сценарий через несколько процессов.

Pytest автоматически ставит маркеры `unit`, `component`, `integration` и `e2e` по первому каталогу внутри `tests/`. Тесты, которым нужен PostgreSQL, Redis или другая инфраструктура, должны лежать в `tests/integration` или `tests/e2e`, иметь соответствующий маркер через путь и явно описывать требуемый сервис в названии фикстуры, docstring или комментарии рядом с настройкой.

## Миграции

```bash
make make-migration name=short_description
make migrate
make migration-check
```

В Docker-стеке миграции при старте выполняет `backend` через `alembic upgrade head`. Для ручного прогона внутри стека:

```bash
make migrate-stack
```

Не правьте уже применённые миграции без отдельного решения по окружениям, где они могли выполниться.

## Proto-файлы

Контракты:

- `src/backend/proto/helpdesk.proto`;
- `src/ai_service/proto/ai_service.proto`.

После изменения:

```bash
make proto
make proto-check
```

`make proto` также исправляет относительные импорты в сгенерированных `*_pb2_grpc.py`.

## Частые рабочие сценарии

### Изменить поведение backend

1. Меняйте use case или service operation в `src/application`.
2. Если меняется внешний контракт, обновите `.proto`, translators, server и client.
3. Добавьте или поправьте tests.
4. Прогоните `make test`, `make typecheck`, при необходимости `make proto-check`.

### Изменить UI бота

1. Текст - `src/bot/texts`.
2. Кнопки - `src/bot/keyboards`.
3. Отображение данных - `src/bot/formatters`.
4. Сценарий - `src/bot/handlers`.

Не переносите правила доступа в UI: скрыть кнопку полезно, но backend всё равно должен отклонять недопустимое действие.

### Изменить UI Mini App

1. API client - `src/mini_app/static/assets/api.js`.
2. Routing/state - `src/mini_app/static/assets/app.js`.
3. Markup renderers - `src/mini_app/static/assets/renderers.js`.
4. Styles - `src/mini_app/static/assets/styles.css`.
5. Backend data shape - `src/mini_app/serializers.py`, `api.py`, `http.py`.

### Изменить экспорты

1. Report shape - `src/application/use_cases/tickets/exports.py` или `src/application/use_cases/analytics/exports.py`.
2. Renderer - `src/infrastructure/exports`.
3. Проверьте CSV escaping и HTML escaping.

### Изменить prompts или результаты AI

1. Prompts - `src/ai_service/service_prompts.py`.
2. Result validation - `src/ai_service/service_results.py`.
3. Operation flow - `src/ai_service/service.py`.
4. Runtime feature flags - `src/application/use_cases/ai/settings.py`.

## Диагностика локального setup

| Симптом | Что проверить |
| --- | --- |
| `make install` не стартует | установлен ли `python3.12`, выполнен ли `poetry env use python3.12` |
| backend не готов | `make logs-backend`, настройки `DATABASE__*`, `REDIS__*`, `AI_SERVICE__*` |
| bot не запускает polling | `APP__DRY_RUN=false` и заданный `TELEGRAM_BOT_TOKEN` |
| Mini App не открывается из Telegram | публичный `HTTPS` в `MINI_APP__PUBLIC_URL`, не `localhost` |
| AI не отвечает | `make logs-ai`, `AI__MODEL_ID`, `AI__LOCAL_MODEL_PATH`, cache volumes |
| `proto-check` падает | выполните `make proto`, затем посмотрите diff generated files |
| `migration-check` падает | проверьте SQLAlchemy models и новую Alembic revision |
