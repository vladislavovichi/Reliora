# Безопасность

Reliora не является отдельной security platform. В проекте есть конкретные защитные границы для Telegram-входа, внутренних сервисов, операторских ролей, вложений, экспортов и AI.

## Threat model в scope

- Telegram-facing bot принимает сообщения, callbacks, команды и вложения.
- Mini App принимает Telegram init data и открывает операторский HTTP API.
- Внутренние gRPC-вызовы идут между `bot`, `mini-app`, `backend`, `ai-service`.
- Operator invites переводят Telegram-пользователя в роль `operator`.
- Вложения скачиваются из Telegram и сохраняются локально.
- Экспорты создают файлы с историей заявки или аналитикой.
- AI provider получает подготовленный контекст для подсказок.

Вне scope: защита инфраструктуры хоста, TLS termination, управление секретами в production, WAF, DLP, SIEM.

## Internal service auth

Backend проверяет metadata:

- `x-helpdesk-internal-token`;
- `x-helpdesk-caller`;
- `x-correlation-id`;
- `x-helpdesk-actor-telegram-user-id`, если нужен actor.

Токен задаётся через `BACKEND_AUTH__TOKEN`. Для `backend -> ai-service` используется отдельный `AI_SERVICE_AUTH__TOKEN`.

Пустые или дефолтные токены нельзя оставлять в production.

## Роли и operator invites

Роли:

- `user` - обычный клиент;
- `operator` - оператор support;
- `super_admin` - оператор с административными действиями.

`super_admin` задаётся конфигурацией `AUTHORIZATION__SUPER_ADMIN_TELEGRAM_USER_IDS`.

Operator invite codes:

- одноразовые;
- имеют срок действия;
- в базе хранится hash, а не исходный код;
- выпуск доступны только `super_admin`;
- погашение пишет audit-события.

UI не является единственной защитой. Backend должен проверять роль для действий, даже если кнопка скрыта.

## Вложения

Принимаются `photo`, `document`, `voice`, `video`.

Защита:

- лимиты размера по типам через `ATTACHMENTS__*`;
- блокировка опасных MIME-types для документов;
- блокировка опасных расширений: `.exe`, `.sh`, `.js`, `.jar`, `.msi`, `.ps1` и похожие;
- нормализация имени файла;
- сохранение только под `ASSETS__PATH`;
- защита от абсолютных путей и `..` при resolve.

Ограничение: проект не выполняет antivirus scanning. Для production с высоким риском вложений добавляйте отдельную проверку на уровне инфраструктуры или storage pipeline.

## Export safety

Экспорты создаются в backend и рендерятся в `src/infrastructure/exports`.

Правила:

- CSV должен экранировать значения, похожие на формулы;
- HTML должен экранировать пользовательский текст;
- вложения в HTML не должны превращаться в небезопасные inline-объекты;
- внутренние заметки в ticket report включаются только при `EXPORTS__INCLUDE_INTERNAL_NOTES_IN_TICKET_REPORTS=true`.

Экспорт может содержать персональные данные и внутренние заметки. Не отправляйте такие файлы в публичные каналы.

## AI safety

AI в Reliora - подсказки, не решения.

- Raw prompts не показываются в UI.
- AI summary, macro suggestions, category prediction и reply draft не меняют заявку сами по себе.
- Черновик ответа не отправляется клиенту автоматически.
- Недоступный AI должен деградировать в понятное состояние, а не ломать helpdesk.
- Не логируйте provider tokens, raw provider payloads и секреты.
- Контекст для AI должен быть минимальным для операции.

Runtime AI settings в Mini App admin могут отключать отдельные функции. `operator_must_review_ai` нормализуется в `true`.

## Secrets и env

В production обязательно заменить:

- `BOT__TOKEN`;
- `BACKEND_AUTH__TOKEN`;
- `AI_SERVICE_AUTH__TOKEN`;
- `DATABASE__PASSWORD`;
- `REDIS__PASSWORD`, если Redis защищён паролем;
- `AI__API_TOKEN`, если AI включён;
- `AUTHORIZATION__SUPER_ADMIN_TELEGRAM_USER_IDS`.

`.env` не должен попадать в публичные артефакты и отчёты.

## Audit

Audit logs пишутся в PostgreSQL таблицу `audit_logs`. Запись содержит действие, сущность, outcome, actor telegram id, entity id/public id, correlation id и metadata.

Audit полезен для:

- разбора операторских действий;
- проверки выпусков и погашений инвайтов;
- разбора экспортов;
- поиска изменений тем, макросов и тегов.

Audit не заменяет централизованные immutable logs production-инфраструктуры.

## Checklist перед deploy

- `APP__DRY_RUN=false` только там, где должен идти Telegram polling.
- `BOT__TOKEN` задан и не является примером.
- `BACKEND_AUTH__TOKEN` и `AI_SERVICE_AUTH__TOKEN` заменены.
- `AUTHORIZATION__SUPER_ADMIN_TELEGRAM_USER_IDS` содержит только нужных администраторов.
- `MINI_APP__PUBLIC_URL` публичный `HTTPS`.
- `EXPORTS__INCLUDE_INTERNAL_NOTES_IN_TICKET_REPORTS` осознанно выбран.
- Backup PostgreSQL и assets настроены отдельно.
- Логи не содержат токены и raw provider payloads.
- `make health` и `make smoke` проходят после запуска.
