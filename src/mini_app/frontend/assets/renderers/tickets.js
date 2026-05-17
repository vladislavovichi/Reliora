import {
  applyTicketFilters,
  escapeAttribute,
  escapeHtml,
  formatDateTime,
  priorityLabel,
  renderEmptyBlock,
  renderFact,
  renderInlineEmpty,
  renderSearchRow,
  senderLabel,
  sentimentLabel,
  statusLabel,
} from "../render-utils.js";
import { renderAiReplyCard, renderMacroList, renderTicketAiCard } from "./ai.js";

export function renderQueue(data, filters) {
  const items = applyTicketFilters(data.items, filters);

  return `
    <section class="surface surface-roomy">
      <div class="surface-head">
        <div>
          <p class="eyebrow">Очередь</p>
          <h2>Новые и свободные заявки</h2>
          <p class="subtitle">Сначала те, что требуют внимания быстрее всего.</p>
        </div>
        <div class="inline-actions">
          <span class="soft-chip">${escapeHtml(String(items.length))} в списке</span>
          <button class="action action-primary" data-action="take-next">Взять следующую</button>
        </div>
      </div>
      ${renderSearchRow("queue-search", "Поиск по номеру или теме", filters.search ?? "")}
      ${renderTicketTable(items, { showTake: true, emptyTitle: "Очередь сейчас спокойна.", mode: "queue" })}
    </section>
  `;
}

export function renderMyTickets(data, filters) {
  const items = applyTicketFilters(data.items, filters);

  return `
    <section class="surface surface-roomy">
      <div class="surface-head">
        <div>
          <p class="eyebrow">Моя зона</p>
          <h2>Назначенные заявки</h2>
          <p class="subtitle">Открытые диалоги и дела, за которые вы отвечаете сейчас.</p>
        </div>
        <span class="soft-chip">${escapeHtml(String(items.length))} в работе</span>
      </div>
      ${renderSearchRow("mine-search", "Поиск по номеру или теме", filters.search ?? "")}
      ${renderTicketTable(items, { showTake: false, emptyTitle: "Активных заявок пока нет.", mode: "mine" })}
    </section>
  `;
}

export function renderTicketWorkspace(data, replyDraftState = null) {
  const ticket = data.ticket;
  const ai = data.ai;
  const canReassign = data.operators.length > 0;
  const lastMessageLabel = ticket.last_message_sender_type
    ? senderLabel(ticket.last_message_sender_type, ticket.assigned_operator_name)
    : "Нет сообщений";

  return `
    <section class="ticket-hero premium-panel">
      <div class="ticket-hero-main">
        <div>
          <p class="eyebrow">${escapeHtml(ticket.public_number)}</p>
          <h2>${escapeHtml(ticket.subject)}</h2>
          <p class="subtitle">
            ${ticket.category_title ? escapeHtml(ticket.category_title) : "Без темы"} ·
            ${escapeHtml(ticket.assigned_operator_name ?? "Свободная заявка")}
          </p>
        </div>
        <div class="ticket-meta-strip">
          <span class="ticket-status-chip status-${escapeAttribute(ticket.status)}">${statusLabel(ticket.status)}</span>
          <span class="ticket-priority-chip priority-${escapeAttribute(ticket.priority)}">${priorityLabel(ticket.priority)}</span>
          <span class="soft-chip">Создана ${formatDateTime(ticket.created_at)}</span>
          <span class="soft-chip">${ticket.closed_at ? `Закрыта ${formatDateTime(ticket.closed_at)}` : "Открыта"}</span>
        </div>
      </div>
      <div class="ticket-action-bar">
        <div class="inline-actions wrap-actions">
          <button class="action action-subtle" data-ticket-action="take">Взять</button>
          <button class="action action-subtle" data-ticket-action="escalate">Эскалировать</button>
          <button class="action action-primary" data-ticket-action="close">Закрыть</button>
        </div>
        <div class="utility-actions utility-actions-end">
          <span class="utility-label">Экспорт</span>
          <button class="action action-subtle" data-ticket-export="html">HTML</button>
          <button class="action action-subtle" data-ticket-export="csv">CSV</button>
        </div>
      </div>
    </section>

    <section class="ticket-workspace-grid">
      <div class="ticket-primary-column">
        <article class="ticket-section premium-panel">
          <div class="subsurface-head">
            <h3>Обзор заявки</h3>
            <span class="soft-chip">${escapeHtml(lastMessageLabel)}</span>
          </div>
          <div class="facts">
            ${renderFact("Статус", statusLabel(ticket.status))}
            ${renderFact("Приоритет", priorityLabel(ticket.priority))}
            ${renderFact("Назначено", ticket.assigned_operator_name ?? "Свободно")}
            ${renderFact("Создана", formatDateTime(ticket.created_at))}
            ${renderFact("Закрыта", ticket.closed_at ? formatDateTime(ticket.closed_at) : "—")}
            ${renderFact("Теги", ticket.tags.length ? ticket.tags.join(", ") : "Нет")}
          </div>
          ${
            ticket.sentiment
              ? `
                <div class="signal-card">
                  <strong>${escapeHtml(sentimentLabel(ticket.sentiment))}</strong>
                  <span>${ticket.sentiment_reason ? escapeHtml(ticket.sentiment_reason) : "Сигнал без пояснения"}</span>
                </div>
              `
              : ""
          }
        </article>

        ${renderTicketAiCard(ai)}

        ${renderAiReplyCard(replyDraftState)}
      </div>

      <aside class="ticket-side-column">
        <article class="ticket-section premium-panel operator-panel">
          <div class="subsurface-head">
            <h3>Действия оператора</h3>
            <span class="soft-chip">Операции</span>
          </div>
          <form class="note-form" id="note-form">
            <label>
              <span>Внутренняя заметка</span>
              <textarea id="note-text" placeholder="Коротко и по делу"></textarea>
            </label>
            <button class="action action-primary" type="submit">Сохранить заметку</button>
          </form>
          ${
            canReassign
              ? `
                <form class="assign-form" id="assign-form">
                  <label>
                    <span>Переназначить</span>
                    <select id="assign-operator">
                      ${data.operators
                        .map(
                          (item) => `
                            <option
                              value="${escapeAttribute(item.telegram_user_id)}"
                              data-display-name="${escapeAttribute(item.display_name)}"
                              data-username="${escapeAttribute(item.username ?? "")}"
                            >
                              ${escapeHtml(item.display_name)}
                            </option>
                          `,
                        )
                        .join("")}
                    </select>
                  </label>
                  <button class="action action-subtle" type="submit">Назначить</button>
                </form>
              `
              : ""
          }
        </article>

        <article class="ticket-section premium-panel macro-panel">
          <div class="subsurface-head">
            <h3>Макросы</h3>
            <span class="soft-chip">Быстрый ответ</span>
          </div>
          <div class="macro-stack">
            ${renderMacroList(data.macros, ai?.macro_suggestions ?? [])}
          </div>
        </article>
      </aside>
    </section>

    <section class="surface-grid ticket-history-grid">
      <article class="surface ticket-section">
        <div class="surface-head">
          <div>
            <p class="eyebrow">Хронология</p>
            <h3>Сообщения</h3>
          </div>
        </div>
        <div class="timeline timeline-premium">
          ${
            ticket.message_history.length
              ? ticket.message_history.map(renderMessage).join("")
              : renderInlineEmpty("Сообщений пока нет.")
          }
        </div>
      </article>
      <article class="surface ticket-section">
        <div class="surface-head">
          <div>
            <p class="eyebrow">Контекст</p>
            <h3>Внутренние заметки</h3>
          </div>
        </div>
        <div class="timeline timeline-premium note-timeline">
          ${
            ticket.internal_notes.length
              ? ticket.internal_notes.map(renderNote).join("")
              : renderInlineEmpty("Заметки ещё не добавлены.")
          }
        </div>
      </article>
    </section>
  `;
}

function renderTicketTable(items, options) {
  if (!items.length) {
    return renderEmptyBlock(options.emptyTitle, "Когда появятся новые дела, они будут показаны здесь.");
  }

  return `
    <div class="ticket-table">
      ${items
        .map(
          (item) => `
            <article class="ticket-row priority-${escapeAttribute(item.priority)} status-${escapeAttribute(item.status)}" data-open-ticket="${escapeAttribute(item.public_id)}">
              <div class="ticket-copy">
                <div class="ticket-row-kicker">
                  <p class="ticket-number">${escapeHtml(item.public_number)}</p>
                  <span class="row-hint">${options.mode === "queue" ? "Свободная" : "Назначенная"}</span>
                </div>
                <h3>${escapeHtml(item.subject)}</h3>
                <div class="meta-row meta-row-wrap ticket-row-meta">
                  <span class="status-chip status-${escapeAttribute(item.status)}">${statusLabel(item.status)}</span>
                  <span class="priority-pill priority-${escapeAttribute(item.priority)}">${priorityLabel(item.priority)}</span>
                  <span class="soft-chip">${item.category_title ? escapeHtml(item.category_title) : "Без темы"}</span>
                </div>
              </div>
              <div class="row-actions">
                ${options.showTake ? `<button class="action" data-take-ticket="${escapeAttribute(item.public_id)}">Взять</button>` : ""}
                <span class="row-hint">Открыть</span>
              </div>
            </article>
          `,
        )
        .join("")}
    </div>
  `;
}

function renderMessage(message) {
  const messageClass = messageClassForSender(message.sender_type);
  return `
    <article class="timeline-item ${messageClass}">
      <div class="timeline-head">
        <strong>${escapeHtml(senderLabel(message.sender_type, message.sender_operator_name))}</strong>
        <span>${formatDateTime(message.created_at)}</span>
      </div>
      ${message.text ? `<div class="timeline-body"><p>${escapeHtml(message.text)}</p></div>` : ""}
      ${message.attachment ? renderAttachment(message.attachment) : ""}
      ${message.duplicate_count > 0 ? `<p class="muted">Повтор: ${escapeHtml(String(message.duplicate_count))}</p>` : ""}
    </article>
  `;
}

function renderNote(note) {
  return `
    <article class="timeline-item note-internal tone-note">
      <div class="timeline-head">
        <strong>${escapeHtml(note.author_operator_name ?? "Оператор")}</strong>
        <span>${formatDateTime(note.created_at)}</span>
      </div>
      <div class="timeline-body"><p>${escapeHtml(note.text)}</p></div>
    </article>
  `;
}

function renderAttachment(attachment) {
  return `
    <div class="attachment-card">
      <strong>${attachment.filename ? escapeHtml(attachment.filename) : escapeHtml(attachment.kind.toUpperCase())}</strong>
      <span>${attachment.mime_type ? escapeHtml(attachment.mime_type) : "Вложение без mime"}</span>
    </div>
  `;
}

function messageClassForSender(senderType) {
  if (senderType === "operator") {
    return "message-operator";
  }
  if (senderType === "system") {
    return "message-system";
  }
  if (senderType === "internal") {
    return "note-internal";
  }
  return "message-customer";
}
