# AI

AI в Reliora используется как помощь оператору. Он не меняет заявку без действия человека и не отправляет ответы клиенту.

## Возможности

- сводка по заявке;
- черновик ответа оператору;
- подсказки подходящих макросов;
- рекомендация темы при создании обращения;
- анализ тональности клиентского сообщения.

gRPC-контракт лежит в `src/ai_service/proto/ai_service.proto`.

## Настройка провайдера

Поддерживаемый внешний provider в коде:

```dotenv
AI__PROVIDER=huggingface
AI__MODEL_ID=Qwen/Qwen3.5-4B
AI__API_TOKEN=hf_xxx
AI__BASE_URL=https://router.huggingface.co/v1/chat/completions
```

Если `AI__PROVIDER=disabled`, `AI__MODEL_ID` пустой или token не задан, провайдер считается отключённым.

`ai-service` всё равно должен быть запущен: backend зависит от его gRPC status.

## Деградация

При отключённом или недоступном провайдере AI-операции возвращают `available=false` и причину недоступности. Основные операции helpdesk продолжают работать.

Примеры:

- нет сводки - карточка заявки открывается без неё;
- нет черновика - оператор пишет сам;
- нет рекомендации темы - заявка создаётся без AI-подсказки;
- нет подсказки макроса - список макросов остаётся обычным.

## Структура prompts и результатов

Код разделён так:

- `src/ai_service/service_prompts.py` - инструкции и сборка prompts;
- `src/ai_service/service.py` - flow операций;
- `src/ai_service/service_results.py` - нормализация и отбраковка слабых результатов;
- `src/ai_service/service_completion.py` - JSON completion и retry/validation;
- `src/application/use_cases/ai/assist.py` - backend-side сборка контекста заявки.

AI-result проходит pydantic schema и дополнительную нормализацию. Слишком короткие, повторяющиеся или общие ответы отбрасываются.

## Настройки AI во время работы

Mini App admin управляет:

- `ai_summaries_enabled`;
- `ai_macro_suggestions_enabled`;
- `ai_reply_drafts_enabled`;
- `ai_category_prediction_enabled`;
- `default_model_id`;
- `max_history_messages`;
- `reply_draft_tone`.

`operator_must_review_ai` нормализуется в `true`.

Настройки хранятся в JSON-файле `AI_RUNTIME_SETTINGS__PATH`, по умолчанию `assets/ai_settings.json`.

## Проверка без реального провайдера

Для локального режима:

```dotenv
AI__PROVIDER=disabled
```

Затем:

```bash
make up
make health
make smoke
```

Smoke покажет warning по provider visibility, но gRPC `ai-service` должен быть доступен.

## Правила безопасности

- Не показывайте raw prompt в UI.
- Не логируйте `AI__API_TOKEN`.
- Не логируйте полный raw provider payload.
- Не отправляйте AI-черновик клиенту автоматически.
- Держите degradation path для каждой AI-функции.
- Перед добавлением нового контекста в prompt проверьте, действительно ли он нужен операции.
