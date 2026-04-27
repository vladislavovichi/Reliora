# Backup и restore PostgreSQL

## Что попадает в backup

`make backup-db` делает логический dump PostgreSQL через `pg_dump -Fc`.

В backup попадают таблицы приложения:

- заявки и сообщения;
- операторы и роли;
- operator invite codes;
- темы, теги и макросы;
- обратная связь;
- audit logs;
- сохранённые AI-сводки и служебные таблицы приложения.

## Что не попадает в backup

- Redis state;
- файлы в `ASSETS__PATH`;
- `.env`;
- Docker images;
- Compose-файлы;
- внешнее состояние Telegram или AI provider.

Если в заявках есть вложения, отдельно сохраняйте каталог assets.

## Создать backup

```bash
make backup-db
```

По умолчанию файл создаётся в:

```text
backups/postgres/helpdesk_YYYYMMDDTHHMMSSZ.dump
```

Свой путь:

```bash
BACKUP_PATH=backups/postgres/before-release.dump make backup-db
```

Скрипт использует значения `DATABASE__DATABASE` и `DATABASE__USER`, по умолчанию `helpdesk`.

## Restore

```bash
BACKUP_PATH=backups/postgres/before-release.dump make restore-db
```

Restore выполняет:

```text
pg_restore --clean --if-exists --no-owner --no-privileges
```

Это перезаписывает объекты в целевой базе. Не запускайте restore в production без подтверждения, что выбран правильный dump и правильное окружение.

## Проверка после restore

```bash
make health
make smoke
```

Дополнительно проверьте вручную:

- operator login/role;
- открытие очереди;
- открытие архивной заявки;
- наличие истории сообщений;
- экспорт заявки;
- если нужны вложения - наличие файлов в `ASSETS__PATH`.

## Локально и в production

Локально restore обычно используется для воспроизведения состояния или проверки миграций. В production restore - аварийная операция: она может удалить данные, созданные после backup.

Перед production restore:

- остановите пользовательскую нагрузку;
- сохраните текущий backup;
- проверьте имя dump-файла;
- проверьте целевой Compose/project;
- оцените совместимость схемы с текущим кодом.
