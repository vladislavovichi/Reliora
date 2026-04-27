# Bot

`bot` - Telegram-слой Reliora. Он отвечает за UX в Telegram, получение updates, отправку сообщений и запуск Mini App. Продуктовые правила остаются в backend.

## Что bot владеет

- команды и callbacks;
- тексты, клавиатуры и форматирование;
- FSM-состояния Telegram-сценариев;
- приём клиентских сообщений и вложений;
- доставку ответов оператора клиенту;
- operator invite onboarding через `/start <code>`;
- кнопку меню `Панель` для Mini App;
- команду `/health` для операторской диагностики.

## Что bot не должен владеть

- правилами переходов статусов заявки;
- проверкой роли как источником истины;
- постоянным хранением истории;
- логикой экспорта;
- прямой работой с AI-провайдером;
- прямым доступом Mini App к данным.

Если handler начинает решать, можно ли закрыть заявку или кто имеет право на действие, это должно уйти в backend/application.

## Основные поверхности

### Клиентский flow

Клиент выбирает тему, отправляет текст или вложение, получает ответы оператора, после закрытия оставляет оценку и комментарий.

Код:

- `src/bot/handlers/user/intake.py`
- `src/bot/handlers/user/workflow.py`
- `src/bot/handlers/user/feedback.py`
- `src/bot/handlers/common/ticket_attachments.py`

### Операторский flow

Оператор видит очередь, берёт заявки, отвечает, применяет макросы, добавляет заметки, управляет тегами, закрывает или эскалирует заявку.

Код:

- `src/bot/handlers/operator/navigation*.py`
- `src/bot/handlers/operator/workflow*.py`
- `src/bot/handlers/operator/tags.py`
- `src/bot/handlers/operator/stats.py`

### Admin flow

`super_admin` управляет операторами, инвайтами, темами и макросами.

Код:

- `src/bot/handlers/admin/*`
- `src/bot/keyboards/inline/admin.py`
- `src/bot/formatters/operator_admin_views.py`

### Mini App launch

Кнопка меню `Панель` синхронизируется при валидном `MINI_APP__PUBLIC_URL`. Если URL пустой или не проходит Telegram-требования, работа остаётся в меню бота.

Код:

- `src/bot/dispatcher.py`
- `src/app/bootstrap.py`
- `src/bot/texts/system.py`

## Карта текстов, клавиатур и handler-ов

| Что менять | Где |
| --- | --- |
| русский текст экрана | `src/bot/texts` |
| inline-кнопки | `src/bot/keyboards/inline` |
| reply menu | `src/bot/keyboards/reply` |
| карточки и списки | `src/bot/formatters` |
| обработка callbacks/messages | `src/bot/handlers` |
| callback payload schemas | `src/bot/callbacks.py` |
| middleware доступа и контекста | `src/bot/middlewares` |

Тон UI: коротко, по делу, без объяснения внутренней архитектуры пользователю. Ошибка должна говорить, что сделать дальше, а не пересказывать stack trace.

## Вложения

Bot принимает:

- `photo`;
- `document`;
- `voice`;
- `video`.

Лимиты задаются через:

- `ATTACHMENTS__PHOTO_MAX_BYTES`;
- `ATTACHMENTS__DOCUMENT_MAX_BYTES`;
- `ATTACHMENTS__VOICE_MAX_BYTES`;
- `ATTACHMENTS__VIDEO_MAX_BYTES`.

Для документов дополнительно блокируются опасные MIME-типы и расширения: `.exe`, `.sh`, `.js`, `.jar`, `.msi`, `.ps1` и похожие. Файлы сохраняются в `ASSETS__PATH` через `LocalTicketAssetStorage`; путь проверяется, чтобы не выйти за пределы корня assets.

## Ошибки и пустые состояния

- Пустая очередь - нормальное состояние, не ошибка.
- Недоступный AI - отсутствие подсказки, а не падение заявки.
- Недоступный backend - честное сообщение о временной недоступности.
- Невалидный Mini App URL - работа продолжается через меню бота.
- Ошибки вложений показываются клиенту простым текстом: неподдерживаемо, слишком большой файл или небезопасный документ.

## Как добавить новое действие оператора

1. Добавьте backend/application действие, если его ещё нет.
2. Расширьте gRPC client/server, если действие вызывается из bot.
3. Добавьте callback schema в `src/bot/callbacks.py`.
4. Добавьте кнопку в `src/bot/keyboards/inline/operator_actions.py` или рядом с нужной поверхностью.
5. Добавьте handler в подходящий `workflow_*` модуль.
6. Обновите formatter, чтобы состояние после действия было понятно.
7. Проверьте права через backend, а не только через скрытие кнопки.

## Как менять экран безопасно

- Сначала найдите formatter, который строит текст.
- Затем найдите keyboard builder для действий.
- Потом меняйте handler только если меняется сценарий.
- Не передавайте aiogram-объекты в application.
- Не кладите бизнес-решение в callback handler.
- Для новых callback data держите payload коротким и совместимым с Telegram limits.

Минимальные проверки:

```bash
make lint
make typecheck
make test
```
