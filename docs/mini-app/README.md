# Mini App

Mini App - операторское рабочее место внутри Telegram. В нём есть обзор, очередь, мои заявки, архив, аналитика, админ-раздел и карточка заявки.

## Что делает Mini App

- проверяет Telegram init data;
- получает роль и профиль пользователя через backend;
- показывает рабочие списки оператора;
- открывает ticket workspace;
- выполняет действия по заявке через backend;
- скачивает экспорты;
- даёт `super_admin` доступ к операторам, инвайтам и AI-настройкам.

Mini App не ходит в PostgreSQL и Redis напрямую.

## Маршруты и экраны

Frontend routes живут в hash:

- `#dashboard` - обзор;
- `#queue` - свободные заявки;
- `#mine` - заявки оператора;
- `#archive` - архив;
- `#analytics` - аналитика;
- `#admin` - админ-раздел для `super_admin`;
- `#ticket/<public_id>` - карточка заявки.

HTTP API:

- `GET /healthz`;
- `GET /api/session`;
- `GET /api/dashboard`;
- `GET /api/queue`;
- `POST /api/queue/take-next`;
- `GET /api/my-tickets`;
- `GET /api/archive`;
- `GET /api/analytics`;
- `GET /api/analytics/export`;
- `GET /api/admin/operators`;
- `GET|PUT /api/admin/ai-settings`;
- `POST /api/admin/invites`;
- `GET /api/tickets/<uuid>`;
- `POST /api/tickets/<uuid>/{take|close|escalate|assign|notes}`;
- `POST /api/tickets/<uuid>/ai-summary`;
- `POST /api/tickets/<uuid>/ai-reply-draft`;
- `POST /api/tickets/<uuid>/macros/<id>`;
- `GET /api/tickets/<uuid>/export`.

## Telegram init data

Mini App принимает init data из:

- `X-Telegram-Init-Data`;
- `Authorization: TMA ...`;
- query `tgWebAppData` или `init_data`.

Подпись проверяется по `BOT__TOKEN`. Возраст запуска ограничен `MINI_APP__INIT_DATA_TTL_SECONDS`.

Если открыть Mini App как обычную web-страницу без Telegram context, API вернёт `401`, а frontend покажет состояние отсутствующего запуска.

## Публичный URL

Для Telegram launch нужен:

```dotenv
MINI_APP__PUBLIC_URL=https://mini-app.example.com
```

Требования:

- только `https://`;
- публичный домен или глобальный IP;
- без `localhost`, `.local`, `.test`, приватных адресов;
- без URL fragment.

Локально используйте:

```bash
make full-cloudflared
```

## Карта frontend-файлов

- `src/mini_app/static/index.html` - HTML shell.
- `src/mini_app/static/assets/app.js` - state, routing, event handling.
- `src/mini_app/static/assets/api.js` - HTTP client.
- `src/mini_app/static/assets/renderers.js` - screens markup.
- `src/mini_app/static/assets/render-utils.js` - helpers.
- `src/mini_app/static/assets/telegram.js` - launch context.
- `src/mini_app/static/assets/styles.css` - стили.

Backend-side Mini App:

- `src/mini_app/http.py` - HTTP routing, auth, errors, file responses.
- `src/mini_app/api.py` - gateway к backend gRPC.
- `src/mini_app/serializers.py` - JSON shape для frontend.
- `src/mini_app/auth.py` - проверка Telegram init data.

## Как менять UI безопасно

- Не добавляйте прямые обращения к backend gRPC во frontend.
- Сначала расширяйте JSON serializer, затем renderer.
- Ошибки API показывайте как рабочие состояния, особенно для AI.
- Для `super_admin` экранов проверяйте доступ на server side (`_require_admin`), а не только скрывайте nav.
- После изменения public URL перезапускайте `bot` и `mini-app`.

## Частые проблемы

| Симптом | Что проверить |
| --- | --- |
| кнопка `Панель` не появляется | `MINI_APP__PUBLIC_URL`, логи `bot`, валидность HTTPS URL |
| `/healthz` отвечает, но Telegram не открывает Mini App | URL локальный или tunnel устарел |
| `401` в API | Mini App открыт не из Telegram или init data истекла |
| `403` в API | пользователь не `operator` и не `super_admin` |
| AI-кнопка возвращает недоступность | provider disabled, rate limit или runtime AI settings |
