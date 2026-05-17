import {
  escapeAttribute,
  escapeHtml,
  formatDateTime,
  renderFact,
  renderInlineEmpty,
} from "../render-utils.js";

const TONE_LABELS = {
  polite: "вежливый",
  friendly: "дружелюбный",
  formal: "формальный",
};

export function renderTicketAiCard(ai) {
  const status = normalizeSummaryStatus(ai?.summary_status);
  const statusText = summaryStatusLabel(status);
  const refreshLabel = status === "missing" ? "Собрать сводку" : "Обновить сводку";

  if (!ai) {
    return `
      <article class="ticket-section premium-panel ai-card is-missing">
        <div class="subsurface-head">
          <div>
            <h3>AI-сводка</h3>
            <p class="subtitle">AI-контекст не вернулся от сервера.</p>
          </div>
          <span class="soft-chip">Нет сводки</span>
        </div>
        <div class="ai-section">
          <p class="empty-inline">Можно продолжать работу по истории сообщений и заметкам.</p>
        </div>
        <button class="action action-primary" data-ticket-ai-refresh type="button">Собрать сводку</button>
      </article>
    `;
  }

  const unavailable = ai.available === false;
  return `
    <article class="ticket-section premium-panel ai-card is-${status}">
      <div class="subsurface-head">
        <div>
          <h3>AI-сводка</h3>
          <p class="subtitle">${unavailable ? "AI-помощник сейчас работает в деградированном режиме." : "Краткий контекст для ответа оператору."}</p>
        </div>
        <span class="soft-chip">${escapeHtml(statusText)}</span>
      </div>
      ${
        status === "stale"
          ? `<div class="ai-warning">После генерации появилась новая активность. Обновите сводку перед ответом.</div>`
          : ""
      }
      ${
        unavailable && ai.unavailable_reason
          ? `<div class="ai-warning">${escapeHtml(ai.unavailable_reason)}</div>`
          : ""
      }
      ${
        unavailable && ai.failure_reason
          ? `<div class="ai-warning">Техническая причина: ${escapeHtml(ai.failure_reason)}</div>`
          : ""
      }
      <div class="ai-section">
        ${renderAiField("Сводка", ai.short_summary)}
        ${renderAiField("Цель клиента", ai.user_goal)}
        ${renderAiField("Что сделано", ai.actions_taken)}
        ${renderAiField("Текущий статус", ai.current_status)}
      </div>
      <div class="facts">
        ${renderFact("Свежесть", statusText)}
        ${renderFact("Сгенерирована", ai.summary_generated_at ? formatDateTime(ai.summary_generated_at) : "—")}
        ${renderFact("Модель", ai.model_id || "—")}
        ${renderFact("Комментарий", ai.status_note || "—")}
      </div>
      <button class="action action-primary" data-ticket-ai-refresh type="button">${refreshLabel}</button>
    </article>
  `;
}

export function renderAiReplyCard(replyDraftState) {
  const payload = replyDraftState?.payload ?? null;
  const isLoading = Boolean(replyDraftState?.loading);
  return `
    <article class="ticket-section premium-panel ai-reply-card">
      <div class="subsurface-head">
        <div>
          <h3>AI-черновик ответа</h3>
          <p class="subtitle">Черновик только для проверки оператором. Автоотправки нет.</p>
        </div>
        <button
          class="action action-primary"
          data-ticket-ai-reply-draft
          type="button"
          ${isLoading ? "disabled" : ""}
        >
          ${isLoading ? "Готовим..." : "Сгенерировать ответ"}
        </button>
      </div>
      ${renderAiReplyDraft(payload, isLoading)}
    </article>
  `;
}

export function renderMacroList(macros, suggestions) {
  const safeSuggestions = Array.isArray(suggestions) ? suggestions : [];
  const suggestionId = (item) => {
    if (typeof item === "string" || typeof item === "number") {
      return String(item);
    }
    return item?.macro_id ? String(item.macro_id) : "";
  };
  const suggestedIds = new Set(safeSuggestions.map(suggestionId).filter(Boolean));
  const macrosById = new Map(macros.map((macro) => [String(macro.id), macro]));
  const suggestedMacros = safeSuggestions
    .map((suggestion) => normalizeMacroSuggestion(suggestion, macrosById))
    .filter((suggestion) => suggestion.macro_id);
  const remainingMacros = macros.filter((macro) => !suggestedIds.has(String(macro.id)));
  const totalCount = suggestedMacros.length + remainingMacros.length;
  if (!totalCount) {
    return renderInlineEmpty("Макросы пока не настроены.");
  }

  return `
    <section class="macro-section macro-quick-actions">
      <div class="macro-section-head">
        <h5>Быстрые действия</h5>
        <span class="soft-chip">${escapeHtml(String(totalCount))}</span>
      </div>
      <div class="macro-card-grid">
        ${suggestedMacros.map(renderMacroSuggestion).join("")}
        ${remainingMacros.map(renderMacroCard).join("")}
      </div>
    </section>
  `;
}

function renderAiReplyDraft(payload, isLoading) {
  if (isLoading) {
    return `<p class="empty-inline">Готовлю безопасный черновик по текущему контексту...</p>`;
  }
  if (!payload) {
    return `<p class="empty-inline">Сгенерируйте черновик, когда нужен быстрый старт ответа клиенту.</p>`;
  }
  if (payload.available === false) {
    return `
      <div class="ai-warning">
        ${escapeHtml(payload.unavailable_reason || "AI-черновик сейчас недоступен.")}
        ${
          payload.failure_reason
            ? `<br><small>Техническая причина: ${escapeHtml(payload.failure_reason)}</small>`
            : ""
        }
      </div>
    `;
  }
  return `
    <div class="ai-reply-draft">
      <p>${escapeHtml(payload.reply_text || "Черновик пуст.")}</p>
      ${
        payload.reply_text
          ? `<button class="action action-subtle copy-draft-button" data-copy-draft type="button">Скопировать черновик</button>`
          : ""
      }
    </div>
    <div class="ai-reply-meta">
      ${payload.tone ? `<span class="soft-chip">Тон: ${escapeHtml(TONE_LABELS[payload.tone] ?? payload.tone)}</span>` : ""}
      ${
        payload.confidence !== null && payload.confidence !== undefined
          ? `<span class="soft-chip">Уверенность: ${escapeHtml(formatConfidence(payload.confidence))}</span>`
          : ""
      }
      ${payload.model_id ? `<span class="soft-chip">Модель: ${escapeHtml(payload.model_id)}</span>` : ""}
    </div>
    ${
      payload.safety_note
        ? `<div class="ai-safety-note">${escapeHtml(payload.safety_note)}</div>`
        : ""
    }
    ${renderMissingInformation(payload.missing_information)}
  `;
}

function renderMissingInformation(items) {
  if (!Array.isArray(items) || !items.length) {
    return "";
  }
  return `
    <div class="ai-missing-info">
      <strong>Не хватает информации</strong>
      <ul>
        ${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
      </ul>
    </div>
  `;
}

function renderAiField(label, value) {
  return `
    <div class="ai-field">
      <span>${escapeHtml(label)}</span>
      <p>${value ? escapeHtml(value) : "—"}</p>
    </div>
  `;
}

function formatConfidence(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return String(value);
  }
  return `${Math.round(numeric * 100)}%`;
}

function renderMacroCard(macro) {
  return `
    <button class="macro-button macro-card" data-apply-macro="${escapeAttribute(macro.id)}">
      <strong>${escapeHtml(macro.title)}</strong>
      <span>${escapeHtml(macro.body)}</span>
    </button>
  `;
}

function normalizeMacroSuggestion(suggestion, macrosById) {
  const normalized =
    typeof suggestion === "string" || typeof suggestion === "number"
      ? { macro_id: String(suggestion) }
      : (suggestion ?? {});
  const macro = macrosById.get(String(normalized.macro_id));
  return {
    macro_id: normalized.macro_id ? String(normalized.macro_id) : "",
    title: normalized.title || macro?.title || "",
    body: normalized.body || macro?.body || "",
    reason: normalized.reason || "",
    confidence: normalized.confidence || "",
  };
}

function renderMacroSuggestion(suggestion) {
  return `
    <button class="macro-button macro-card macro-suggestion is-recommended" data-apply-macro="${escapeAttribute(suggestion.macro_id)}">
      <span class="macro-recommendation-badge">Рекомендовано</span>
      <strong>${escapeHtml(suggestion.title || `Макрос ${suggestion.macro_id}`)}</strong>
      <span>${escapeHtml(suggestion.body || "Быстрый ответ из библиотеки макросов.")}</span>
      <small>
        ${suggestion.reason ? escapeHtml(suggestion.reason) : "AI-рекомендация"}
        ${suggestion.confidence ? ` · ${escapeHtml(confidenceLabel(suggestion.confidence))}` : ""}
      </small>
    </button>
  `;
}

function normalizeSummaryStatus(status) {
  return ["fresh", "stale", "missing"].includes(status) ? status : "missing";
}

function summaryStatusLabel(status) {
  return {
    fresh: "Свежая",
    stale: "Нужно обновить",
    missing: "Нет сводки",
  }[status];
}

function confidenceLabel(confidence) {
  return {
    high: "высокая уверенность",
    medium: "средняя уверенность",
    low: "низкая уверенность",
    none: "нет уверенности",
  }[confidence] ?? confidence;
}
