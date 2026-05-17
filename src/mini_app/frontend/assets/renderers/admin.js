import { escapeAttribute, escapeHtml, formatDateTime, renderInlineEmpty } from "../render-utils.js";

const TONE_LABELS = {
  polite: "вежливый",
  friendly: "дружелюбный",
  formal: "формальный",
};

export function renderAdmin(data, invite, aiSettingsDraft = null) {
  const operators = data.operators?.items ?? data.items ?? [];
  const aiSettings = aiSettingsDraft ?? data.aiSettings?.settings ?? {};
  return `
    <section class="surface-grid">
      <article class="surface surface-roomy">
        <div class="surface-head">
          <div>
            <p class="eyebrow">Команда</p>
            <h2>Операторы</h2>
            <p class="subtitle">Состав дежурной команды и быстрый выпуск инвайтов.</p>
          </div>
          <button class="action action-primary" data-action="create-invite">Создать инвайт</button>
        </div>
        ${invite ? renderInviteCard(invite) : ""}
        <div class="operator-list">
          ${
            operators.length
              ? operators
                  .map(
                    (item) => `
                      <article class="operator-row">
                        <div>
                          <strong>${escapeHtml(item.display_name)}</strong>
                          <p class="subtitle">
                            ${item.username ? `@${escapeHtml(item.username)}` : "Без юзернейма"} ·
                            ${escapeHtml(String(item.telegram_user_id))}
                          </p>
                        </div>
                        <span class="status-chip ${item.is_active ? "status-chip-live" : ""}">
                          ${item.is_active ? "Активен" : "Выключен"}
                        </span>
                      </article>
                    `,
                  )
                  .join("")
              : renderInlineEmpty("Операторы пока не добавлены.")
          }
        </div>
      </article>
      <article class="surface surface-roomy surface-quiet">
        <div class="surface-head">
          <div>
            <p class="eyebrow">AI</p>
            <h2>Безопасные настройки</h2>
            <p class="subtitle">Сводки, черновики и рекомендации работают только как помощь оператору.</p>
          </div>
        </div>
        ${renderAISettingsForm(aiSettings)}
      </article>
    </section>
  `;
}

function renderInviteCard(invite) {
  const deepLink = typeof invite.telegram_deep_link === "string" ? invite.telegram_deep_link : "";
  const code = typeof invite.code === "string" ? invite.code : "";
  const maxUses = Number(invite.max_uses);
  const maxUsesLabel = maxUses === 1 ? "Одноразовый доступ" : `Использований: ${maxUses || "—"}`;
  return `
    <section class="invite-card invite-share-card">
      <div class="invite-share-head">
        <div>
          <p class="eyebrow">Новый доступ</p>
          <h3>Инвайт для оператора</h3>
          <p class="subtitle">Отправьте ссылку будущему оператору. После перехода он подтвердит имя в боте.</p>
        </div>
        <span class="soft-chip">${escapeHtml(maxUsesLabel)}</span>
      </div>
      ${
        deepLink
          ? `
            <div class="invite-link-field">
              <span>Ссылка Telegram</span>
              <strong>${escapeHtml(deepLink)}</strong>
            </div>
          `
          : `
            <div class="invite-link-field is-unavailable">
              <span>Ссылка Telegram</span>
              <strong>Недоступна</strong>
              <small>${invite.link_unavailable_reason === "bot_username_missing"
                ? "Имя бота не настроено. Отправьте оператору код вручную."
                : "Ссылку пока нельзя собрать автоматически."}</small>
            </div>
          `
      }
      <div class="invite-code-field">
        <span>Код инвайта</span>
        <strong>${escapeHtml(code)}</strong>
      </div>
      <div class="invite-meta-row">
        <span>Действует до ${formatDateTime(invite.expires_at)}</span>
        <span class="invite-security-note">Не пересылайте ссылку посторонним.</span>
      </div>
      <div class="invite-actions">
        ${
          deepLink
            ? `
              <button
                class="action action-primary"
                data-copy="${escapeAttribute(deepLink)}"
                data-copy-success="Ссылка скопирована."
                type="button"
              >
                Скопировать ссылку
              </button>
              <a
                class="action action-subtle"
                href="${escapeAttribute(deepLink)}"
                target="_blank"
                rel="noopener noreferrer"
              >
                Открыть в Telegram
              </a>
            `
            : ""
        }
        <button
          class="action ${deepLink ? "action-subtle" : "action-primary"}"
          data-copy="${escapeAttribute(code)}"
          data-copy-success="Код скопирован."
          type="button"
        >
          Скопировать код
        </button>
      </div>
    </section>
  `;
}

function renderAISettingsForm(settings) {
  const maxHistory = Number.isFinite(Number(settings.max_history_messages))
    ? Number(settings.max_history_messages)
    : 20;
  const tone = settings.reply_draft_tone || "polite";
  return `
    <form class="settings-form" id="ai-settings-form">
      <div class="settings-toggle-grid">
        ${renderSettingsToggle(
          "ai_summaries_enabled",
          "AI-сводки",
          "Собирают короткий контекст заявки для оператора.",
          settings.ai_summaries_enabled !== false,
        )}
        ${renderSettingsToggle(
          "ai_macro_suggestions_enabled",
          "Подбор макросов",
          "Предлагают готовые ответы по контексту диалога.",
          settings.ai_macro_suggestions_enabled !== false,
        )}
        ${renderSettingsToggle(
          "ai_reply_drafts_enabled",
          "Черновики ответов",
          "Готовят текст, который оператор проверяет перед отправкой.",
          settings.ai_reply_drafts_enabled !== false,
        )}
        ${renderSettingsToggle(
          "ai_category_prediction_enabled",
          "Определение темы",
          "Помогает выбрать категорию по безопасному контексту заявки.",
          settings.ai_category_prediction_enabled !== false,
        )}
      </div>

      <label class="settings-field">
        <span>Модель по умолчанию</span>
        <input
          name="default_model_id"
          type="text"
          value="${escapeAttribute(settings.default_model_id || "")}"
          placeholder="По умолчанию из окружения"
          autocomplete="off"
        />
      </label>

      <div class="settings-row">
        <label class="settings-field">
          <span>Глубина истории</span>
          <input
            name="max_history_messages"
            type="number"
            min="1"
            max="100"
            step="1"
            value="${escapeAttribute(String(maxHistory))}"
          />
        </label>
        <label class="settings-field">
          <span>Тон ответа</span>
          <select name="reply_draft_tone">
            ${["polite", "friendly", "formal"]
              .map(
                (value) => `
                  <option value="${value}" ${tone === value ? "selected" : ""}>
                    ${TONE_LABELS[value]}
                  </option>
                `,
              )
              .join("")}
          </select>
        </label>
      </div>

      <div class="settings-review-note">
        <strong>Проверка оператором обязательна</strong>
        <span>AI-ответы остаются черновиками. Секреты провайдера и API-ключи здесь не показываются.</span>
      </div>

      <div class="inline-actions">
        <button class="action action-primary" type="submit">Сохранить</button>
        <button class="action action-subtle" data-ai-settings-cancel type="button">Отменить</button>
      </div>
    </form>
  `;
}

function renderSettingsToggle(name, title, description, checked) {
  return `
    <label class="settings-toggle">
      <input name="${escapeAttribute(name)}" type="checkbox" ${checked ? "checked" : ""} />
      <span>
        <strong>${escapeHtml(title)}</strong>
        <small>${escapeHtml(description)}</small>
      </span>
    </label>
  `;
}
