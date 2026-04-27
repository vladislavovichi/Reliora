# Экспорты

Reliora отдаёт `HTML` и `CSV` выгрузки по заявке и по аналитике. Экспорт создаётся backend-ом; Bot и Mini App только запрашивают файл.

## Отчёт по заявке

Форматы:

- `html`;
- `csv`.

В отчёт по заявке входят:

- public id и public number;
- статус, priority, тема;
- назначенный оператор;
- timestamps создания, обновления, первого ответа и закрытия;
- category;
- sentiment-сигналы;
- tags;
- feedback;
- история сообщений;
- сведения о вложениях;
- релевантные события workflow;
- внутренние заметки, если `EXPORTS__INCLUDE_INTERNAL_NOTES_IN_TICKET_REPORTS=true`.

Код:

- `src/application/use_cases/tickets/exports.py`;
- `src/infrastructure/exports/ticket_report_html.py`;
- `src/infrastructure/exports/ticket_report_csv.py`.

## Экспорт аналитики

Форматы:

- `html`;
- `csv`.

Секции:

- `overview`;
- `operators`;
- `topics`;
- `quality`;
- `sla`.

Окна:

- `today`;
- `7d`;
- `30d`;
- `all`.

Код:

- `src/application/use_cases/analytics/exports.py`;
- `src/application/services/stats.py`;
- `src/infrastructure/exports/analytics_snapshot_html.py`;
- `src/infrastructure/exports/analytics_snapshot_csv.py`.

## Правила безопасности

- CSV должен экранировать формулы.
- HTML должен экранировать пользовательский текст.
- Не добавляйте raw JSON provider payload в отчёты.
- Не включайте внутренние заметки без проверки `EXPORTS__INCLUDE_INTERNAL_NOTES_IN_TICKET_REPORTS`.
- Помните, что экспорт может содержать персональные данные и внутренние комментарии.

## Как добавить поле

1. Добавьте поле в report/snapshot dataclass.
2. Протяните значение из repository или service.
3. Обновите `HTML` и `CSV` renderer.
4. Проверьте escaping.
5. Добавьте или обновите тесты, если поле пользовательское или чувствительное.
