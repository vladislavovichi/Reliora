import {
  applyTicketFilters,
  escapeAttribute,
  escapeHtml,
  formatDateTime,
  formatDuration,
  priorityLabel,
  renderBar,
  renderEmptyBlock,
  renderFact,
  renderInlineEmpty,
  renderMetric,
  renderSearchRow,
  senderLabel,
  sentimentLabel,
  statusLabel,
} from "./render-utils.js";

const ROUTE_LABELS = {
  dashboard: "Обзор",
  queue: "Очередь",
  mine: "Мои заявки",
  archive: "Архив",
  analytics: "Аналитика",
  admin: "Управление",
};

export function buildNavigation(role, currentRoute) {
  const routes = ["dashboard", "queue", "mine", "archive", "analytics"];
  if (role === "super_admin") {
    routes.push("admin");
  }

  return routes
    .map(
      (route) => `
        <button class="nav-pill ${currentRoute === route ? "is-active" : ""}" data-route="${route}">
          <span>${ROUTE_LABELS[route]}</span>
        </button>
      `,
    )
    .join("");
}

export function renderAccessDenied(message) {
  return `
    <section class="state-panel">
      <p class="eyebrow">Mini App</p>
      <h2>Доступ закрыт</h2>
      <p class="subtitle">${escapeHtml(message)}</p>
    </section>
  `;
}

export function renderInitDataMissing(copy) {
  return `
    <section class="state-panel">
      <p class="eyebrow">Mini App</p>
      <h2>${escapeHtml(copy?.title ?? "Откройте рабочее место из Telegram")}</h2>
      <p class="subtitle">${escapeHtml(copy?.message ?? "Для безопасного входа нужен запуск из бота.")}</p>
      ${
        copy?.detail
          ? `<p class="launch-detail">${escapeHtml(copy.detail)}</p>`
          : ""
      }
    </section>
  `;
}

export function renderDashboard(data) {
  const snapshot = data.snapshot;

  return `
    <section class="hero-grid">
      <article class="hero-card hero-card-primary">
        <div class="section-caption">
          <p class="eyebrow">Текущий срез</p>
          <span class="soft-chip">За 7 дней</span>
        </div>
        <div class="hero-value">${escapeHtml(String(snapshot.total_open_tickets))}</div>
        <p class="hero-copy">
          Открытых заявок сейчас. В очереди ${escapeHtml(String(snapshot.queued_tickets_count))},
          эскалаций ${escapeHtml(String(snapshot.escalated_tickets_count))}.
        </p>
        <div class="inline-actions">
          <button class="action action-primary" data-action="take-next">Взять следующую</button>
          <button class="action" data-route="queue">Открыть очередь</button>
        </div>
      </article>
      <article class="hero-card hero-card-secondary">
        <div class="section-caption">
          <p class="eyebrow">Ритм команды</p>
          <span class="soft-chip">Живой контур</span>
        </div>
        <div class="metric-board metric-board-compact">
          ${renderMetric("Создано", snapshot.period_created_tickets_count)}
          ${renderMetric("Закрыто", snapshot.period_closed_tickets_count)}
          ${renderMetric("Первый ответ", formatDuration(snapshot.average_first_response_time_seconds))}
          ${renderMetric("Решение", formatDuration(snapshot.average_resolution_time_seconds))}
        </div>
      </article>
    </section>

    <section class="surface-grid surface-grid-three">
      ${renderTicketPreviewCard("Очередь", "Самое срочное сейчас", data.queue_preview, "queue")}
      ${renderTicketPreviewCard("Мои заявки", "Текущая нагрузка", data.my_tickets_preview, "mine")}
      ${renderTicketPreviewCard("Риск SLA", "Кейсы с повышенным вниманием", data.escalations, "queue")}
    </section>

    <section class="surface-grid">
      <article class="surface">
        <div class="surface-head">
          <div>
            <p class="eyebrow">Недавняя история</p>
            <h3>Закрытые заявки</h3>
          </div>
          <button class="action" data-route="archive">Архив</button>
        </div>
        ${renderArchiveRows(data.recent_archive)}
      </article>
      <article class="surface">
        <div class="surface-head">
          <div>
            <p class="eyebrow">Качество</p>
            <h3>Сигналы по сервису</h3>
          </div>
          <button class="action" data-route="analytics">Аналитика</button>
        </div>
        <div class="stats-stack">
          ${renderMetric("Средняя оценка", snapshot.satisfaction_average ? snapshot.satisfaction_average.toFixed(1) : "—")}
          ${renderMetric("Покрытие отзывов", snapshot.feedback_coverage_percent ? `${snapshot.feedback_coverage_percent}%` : "—")}
          ${renderMetric("Нарушения первого ответа", snapshot.first_response_breach_count)}
          ${renderMetric("Нарушения решения", snapshot.resolution_breach_count)}
        </div>
        <div class="bars">
          ${snapshot.top_categories.length
            ? snapshot.top_categories
                .slice(0, 4)
                .map((item) =>
                  renderBar(
                    item.category_title,
                    item.created_ticket_count,
                    snapshot.period_created_tickets_count || 1,
                  ),
                )
                .join("")
            : renderInlineEmpty("Темы пока не накопили статистику.")}
        </div>
      </article>
    </section>
  `;
}

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
      ${renderTicketTable(items, { showTake: true, emptyTitle: "Очередь сейчас спокойна." })}
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
      ${renderTicketTable(items, { showTake: false, emptyTitle: "Активных заявок пока нет." })}
    </section>
  `;
}

export function renderArchive(data, filters) {
  const categories = Array.from(new Set(data.items.map((item) => item.category_title).filter(Boolean)));
  const items = data.items.filter((item) => {
    const matchesSearch = matchesTicketSearch(item, filters.search ?? "");
    const matchesCategory = !filters.category || item.category_title === filters.category;
    return matchesSearch && matchesCategory;
  });

  return `
    <section class="surface surface-roomy">
      <div class="surface-head">
        <div>
          <p class="eyebrow">Архив</p>
          <h2>Закрытые и обработанные</h2>
          <p class="subtitle">История по делам без визуального шума и лишних действий.</p>
        </div>
        <span class="soft-chip">${escapeHtml(String(items.length))} найдено</span>
      </div>
      <div class="toolbar toolbar-wrap">
        ${renderSearchRow("archive-search", "Поиск по номеру или описанию", filters.search ?? "")}
        <label class="select-field">
          <span>Тема</span>
          <select id="archive-category">
            <option value="">Все темы</option>
            ${categories
              .map(
                (category) => `
                  <option value="${escapeAttribute(category)}" ${filters.category === category ? "selected" : ""}>
                    ${escapeHtml(category)}
                  </option>
                `,
              )
              .join("")}
          </select>
        </label>
      </div>
      ${renderArchiveRows(items, true)}
    </section>
  `;
}

export function renderAnalytics(data, windowKey) {
  const snapshot = data.snapshot;
  const windows = [
    ["today", "Сегодня"],
    ["7d", "7 дней"],
    ["30d", "30 дней"],
    ["all", "Всё время"],
  ];

  return `
    <section class="surface surface-roomy">
      <div class="surface-head">
        <div>
          <p class="eyebrow">Аналитика</p>
          <h2>Рабочая картина</h2>
          <p class="subtitle">Ключевые метрики по нагрузке, качеству и SLA.</p>
        </div>
        <div class="inline-actions">
          <button class="action" data-export-analytics="html">HTML</button>
          <button class="action" data-export-analytics="csv">CSV</button>
        </div>
      </div>
      <div class="segmented-control">
        ${windows
          .map(
            ([value, label]) => `
              <button class="segmented ${windowKey === value ? "is-active" : ""}" data-window="${value}">
                ${label}
              </button>
            `,
          )
          .join("")}
      </div>
      <div class="metric-board">
        ${renderMetric("Открыто", snapshot.total_open_tickets)}
        ${renderMetric("Очередь", snapshot.queued_tickets_count)}
        ${renderMetric("Назначено", snapshot.assigned_tickets_count)}
        ${renderMetric("Эскалации", snapshot.escalated_tickets_count)}
        ${renderMetric("Средняя оценка", snapshot.satisfaction_average ? snapshot.satisfaction_average.toFixed(1) : "—")}
        ${renderMetric("Покрытие отзывов", snapshot.feedback_coverage_percent ? `${snapshot.feedback_coverage_percent}%` : "—")}
      </div>
      <div class="surface-grid">
        <article class="subsurface">
          <div class="subsurface-head">
            <h3>Темы</h3>
            <span class="soft-chip">По входящему потоку</span>
          </div>
          <div class="bars">
            ${snapshot.top_categories.length
              ? snapshot.top_categories
                  .slice(0, 6)
                  .map((item) =>
                    renderBar(
                      item.category_title,
                      item.created_ticket_count,
                      snapshot.period_created_tickets_count || 1,
                    ),
                  )
                  .join("")
              : renderInlineEmpty("Темы ещё не накопили историю.")}
          </div>
        </article>
        <article class="subsurface">
          <div class="subsurface-head">
            <h3>Команда</h3>
            <span class="soft-chip">По закрытиям</span>
          </div>
          <div class="bars">
            ${snapshot.operator_snapshots.length
              ? snapshot.operator_snapshots
                  .slice(0, 6)
                  .map((item) =>
                    renderBar(
                      item.display_name,
                      item.closed_ticket_count,
                      snapshot.period_closed_tickets_count || 1,
                      `${item.closed_ticket_count} закрыто`,
                    ),
                  )
                  .join("")
              : renderInlineEmpty("Статистика по команде появится после активности.")}
          </div>
        </article>
      </div>
      <div class="surface-grid">
        <article class="subsurface">
          <div class="subsurface-head">
            <h3>Распределение оценок</h3>
            <span class="soft-chip">Обратная связь</span>
          </div>
          <div class="bars">
            ${snapshot.rating_distribution.length
              ? snapshot.rating_distribution
                  .map((item) => renderBar(`${item.rating} / 5`, item.count, snapshot.feedback_count || 1))
                  .join("")
              : renderInlineEmpty("Оценок пока нет.")}
          </div>
        </article>
        <article class="subsurface">
          <div class="subsurface-head">
            <h3>SLA</h3>
            <span class="soft-chip">Контроль сроков</span>
          </div>
          <div class="stats-stack">
            ${renderMetric("Первый ответ", snapshot.first_response_breach_count)}
            ${renderMetric("Решение", snapshot.resolution_breach_count)}
          </div>
          <div class="bars">
            ${snapshot.sla_categories.length
              ? snapshot.sla_categories
                  .slice(0, 5)
                  .map((item) =>
                    renderBar(
                      item.category_title,
                      item.sla_breach_count,
                      Math.max(snapshot.first_response_breach_count + snapshot.resolution_breach_count, 1),
                    ),
                  )
                  .join("")
              : renderInlineEmpty("Нарушений SLA не зафиксировано.")}
          </div>
        </article>
      </div>
    </section>
  `;
}

export function renderAdmin(data, invite) {
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
        ${
          invite
            ? `
              <div class="invite-card">
                <div>
                  <p class="eyebrow">Новый код</p>
                  <h3>${escapeHtml(invite.code)}</h3>
                  <p class="subtitle">Действует до ${formatDateTime(invite.expires_at)}.</p>
                </div>
                <button class="action" data-copy="${escapeAttribute(invite.code)}">Скопировать</button>
              </div>
            `
            : ""
        }
        <div class="operator-list">
          ${
            data.items.length
              ? data.items
                  .map(
                    (item) => `
                      <article class="operator-row">
                        <div>
                          <strong>${escapeHtml(item.display_name)}</strong>
                          <p class="subtitle">
                            ${item.username ? `@${escapeHtml(item.username)}` : "Без username"} ·
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
            <p class="eyebrow">Контроль</p>
            <h2>Спокойное управление</h2>
          </div>
        </div>
        <p class="subtitle">
          Здесь остаются только ежедневные действия: состав команды и одноразовые инвайты.
          Остальные продуктовые сценарии продолжают жить в backend и bot-слое.
        </p>
      </article>
    </section>
  `;
}

export function renderTicketWorkspace(data) {
  const ticket = data.ticket;
  const ai = data.ai;
  const canReassign = data.operators.length > 0;

  return `
    <section class="surface surface-roomy">
      <div class="surface-head surface-head-tight">
        <div>
          <p class="eyebrow">${escapeHtml(ticket.public_number)}</p>
          <h2>${escapeHtml(ticket.subject)}</h2>
          <div class="meta-row meta-row-wrap">
            <span class="soft-chip">${statusLabel(ticket.status)}</span>
            <span class="soft-chip">${priorityLabel(ticket.priority)}</span>
            <span class="soft-chip">${ticket.category_title ? escapeHtml(ticket.category_title) : "Без темы"}</span>
          </div>
        </div>
        <div class="inline-actions wrap-actions">
          <button class="action" data-ticket-export="html">HTML</button>
          <button class="action" data-ticket-export="csv">CSV</button>
          <button class="action" data-ticket-action="take">Взять</button>
          <button class="action" data-ticket-action="escalate">Эскалировать</button>
          <button class="action action-primary" data-ticket-action="close">Закрыть</button>
        </div>
      </div>

      <div class="workspace-grid">
        <article class="subsurface">
          <div class="subsurface-head">
            <h3>Сводка</h3>
            <span class="soft-chip">Карточка</span>
          </div>
          ${
            ai?.short_summary
              ? `<p class="lead">${escapeHtml(ai.short_summary)}</p>`
              : `<p class="subtitle">AI-сводка пока недоступна. Основной контекст остаётся в истории сообщений и заметках.</p>`
          }
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

        <article class="subsurface">
          <div class="subsurface-head">
            <h3>Действия</h3>
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
                              value="${item.telegram_user_id}"
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
                  <button class="action" type="submit">Назначить</button>
                </form>
              `
              : ""
          }
          <div class="macro-stack">
            <div class="subsurface-head">
              <h4>Макросы</h4>
              <span class="soft-chip">Быстрый ответ</span>
            </div>
            ${renderMacroList(data.macros, ai?.macro_suggestions ?? [])}
          </div>
        </article>
      </div>
    </section>

    <section class="surface-grid">
      <article class="surface">
        <div class="surface-head">
          <div>
            <p class="eyebrow">Хронология</p>
            <h3>Сообщения</h3>
          </div>
        </div>
        <div class="timeline">
          ${
            ticket.message_history.length
              ? ticket.message_history.map(renderMessage).join("")
              : renderInlineEmpty("Сообщений пока нет.")
          }
        </div>
      </article>
      <article class="surface">
        <div class="surface-head">
          <div>
            <p class="eyebrow">Контекст</p>
            <h3>Внутренние заметки</h3>
          </div>
        </div>
        <div class="timeline">
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

export function renderError(message) {
  return `
    <section class="state-panel">
      <p class="eyebrow">Ошибка</p>
      <h2>Не удалось загрузить данные</h2>
      <p class="subtitle">${escapeHtml(message)}</p>
    </section>
  `;
}

export function renderLoading() {
  return `
    <section class="loading-state">
      <div class="loading-stack">
        <div class="loading-line loading-line-wide"></div>
        <div class="loading-line"></div>
      </div>
      <div class="loading-grid">
        <div class="loading-card"></div>
        <div class="loading-card"></div>
        <div class="loading-card"></div>
      </div>
    </section>
  `;
}

function renderTicketPreviewCard(title, subtitle, items, route) {
  return `
    <article class="surface surface-compact">
      <div class="surface-head">
        <div>
          <p class="eyebrow">${escapeHtml(title)}</p>
          <h3>${escapeHtml(subtitle)}</h3>
        </div>
        <button class="action" data-route="${route}">Открыть</button>
      </div>
      <div class="ticket-table ticket-table-compact">
        ${
          items.length
            ? items.map(renderTicketRow).join("")
            : renderInlineEmpty("Сейчас пусто.")
        }
      </div>
    </article>
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
            <article class="ticket-row" data-open-ticket="${item.public_id}">
              <div class="ticket-copy">
                <p class="ticket-number">${escapeHtml(item.public_number)}</p>
                <h3>${escapeHtml(item.subject)}</h3>
                <p class="subtitle">
                  ${item.category_title ? escapeHtml(item.category_title) : "Без темы"} ·
                  ${statusLabel(item.status)} · ${priorityLabel(item.priority)}
                </p>
              </div>
              <div class="row-actions">
                ${options.showTake ? `<button class="action" data-take-ticket="${item.public_id}">Взять</button>` : ""}
                <button class="action action-primary" data-open-ticket="${item.public_id}">Открыть</button>
              </div>
            </article>
          `,
        )
        .join("")}
    </div>
  `;
}

function renderArchiveRows(items, full = false) {
  if (!items.length) {
    return renderEmptyBlock("Архив пока пуст.", "Закрытые дела появятся здесь автоматически.");
  }

  return `
    <div class="archive-list">
      ${items
        .map(
          (item) => `
            <article class="archive-row" data-open-ticket="${item.public_id}">
              <div class="ticket-copy">
                <p class="ticket-number">${escapeHtml(item.public_number)}</p>
                <h3>${escapeHtml(item.mini_title)}</h3>
                <p class="subtitle">
                  ${item.category_title ? escapeHtml(item.category_title) : "Без темы"} ·
                  ${item.closed_at ? formatDateTime(item.closed_at) : formatDateTime(item.created_at)}
                </p>
              </div>
              ${full ? `<button class="action action-primary" data-open-ticket="${item.public_id}">Открыть</button>` : ""}
            </article>
          `,
        )
        .join("")}
    </div>
  `;
}

function renderTicketRow(item) {
  return `
    <article class="ticket-row compact-row" data-open-ticket="${item.public_id}">
      <div class="ticket-copy">
        <p class="ticket-number">${escapeHtml(item.public_number)}</p>
        <h3>${escapeHtml(item.subject)}</h3>
        <p class="subtitle">
          ${item.category_title ? escapeHtml(item.category_title) : "Без темы"} ·
          ${statusLabel(item.status)}
        </p>
      </div>
      <span class="priority-pill priority-${escapeAttribute(item.priority)}">${priorityLabel(item.priority)}</span>
    </article>
  `;
}

function renderMessage(message) {
  return `
    <article class="timeline-item">
      <div class="timeline-head">
        <strong>${senderLabel(message.sender_type, message.sender_operator_name)}</strong>
        <span>${formatDateTime(message.created_at)}</span>
      </div>
      ${message.text ? `<p>${escapeHtml(message.text)}</p>` : ""}
      ${message.attachment ? renderAttachment(message.attachment) : ""}
      ${message.duplicate_count > 0 ? `<p class="muted">Повтор: ${message.duplicate_count}</p>` : ""}
    </article>
  `;
}

function renderNote(note) {
  return `
    <article class="timeline-item tone-note">
      <div class="timeline-head">
        <strong>${escapeHtml(note.author_operator_name ?? "Оператор")}</strong>
        <span>${formatDateTime(note.created_at)}</span>
      </div>
      <p>${escapeHtml(note.text)}</p>
    </article>
  `;
}

function renderAttachment(attachment) {
  return `
    <div class="attachment-card">
      <strong>${attachment.filename ? escapeHtml(attachment.filename) : attachment.kind.toUpperCase()}</strong>
      <span>${attachment.mime_type ? escapeHtml(attachment.mime_type) : "Вложение без mime"}</span>
    </div>
  `;
}

function renderMacroList(macros, suggestions) {
  const suggestedIds = new Set(suggestions.map((item) => item.macro_id));
  if (!macros.length) {
    return renderInlineEmpty("Макросы ещё не созданы.");
  }

  return macros
    .slice(0, 8)
    .map(
      (macro) => `
        <button class="macro-button ${suggestedIds.has(macro.id) ? "is-suggested" : ""}" data-apply-macro="${macro.id}">
          <strong>${escapeHtml(macro.title)}</strong>
          <span>${escapeHtml(macro.body)}</span>
        </button>
      `,
    )
    .join("");
}
