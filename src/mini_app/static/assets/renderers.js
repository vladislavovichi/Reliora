import {
  applyArchiveFilters,
  applyTicketFilters,
  escapeAttribute,
  escapeHtml,
  findArchiveCategory,
  formatDateTime,
  formatDuration,
  priorityLabel,
  buildArchiveCategories,
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
      <div class="state-badge-row">
        <p class="eyebrow">Mini App</p>
        <span class="soft-chip">Безопасный вход</span>
      </div>
      <h2>${escapeHtml(copy?.title ?? "Откройте рабочее место из Telegram")}</h2>
      <p class="subtitle">${escapeHtml(copy?.message ?? "Для безопасного входа нужен запуск из бота.")}</p>
      ${
        copy?.detail
          ? `<p class="launch-detail">${escapeHtml(copy.detail)}</p>`
          : ""
      }
      <div class="state-hints">
        <p>Откройте Mini App через кнопку меню «Рабочее место» в чате с ботом.</p>
        <p>Если проблема повторяется, закройте окно и запустите рабочее место заново.</p>
      </div>
    </section>
  `;
}

export function renderDashboard(data) {
  const snapshot = data.snapshot;
  const buckets = data.operator_dashboard?.buckets ?? data.buckets ?? {};
  const sections = data.operator_dashboard?.sections ?? data.sections ?? {
    needs_attention: [
      "sla_breached_tickets",
      "sla_at_risk_tickets",
      "escalated_tickets",
      "negative_sentiment_tickets",
    ],
    my_work: ["my_active_tickets", "tickets_without_operator_reply"],
    queue: ["unassigned_open_tickets", "tickets_without_category"],
  };

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
        </div>
        <p class="hero-note">Если нужен конкретный кейс, откройте очередь или свои заявки через навигацию.</p>
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

    <section class="surface surface-roomy">
      <div class="surface-head">
        <div>
          <p class="eyebrow">Операторская очередь</p>
          <h2>Что обработать сейчас</h2>
          <p class="subtitle">Сначала риски SLA, эскалации и диалоги, где нужен ваш ответ.</p>
        </div>
      </div>
      <div class="dashboard-grid">
        ${renderDashboardBucketSection("Needs attention", sections.needs_attention, buckets)}
        ${renderDashboardBucketSection("My work", sections.my_work, buckets)}
        ${renderDashboardBucketSection("Queue", sections.queue, buckets)}
      </div>
    </section>

    <section class="surface-grid">
      <article class="surface">
        <div class="surface-head">
          <div>
            <p class="eyebrow">Недавняя история</p>
            <h3>Закрытые заявки</h3>
          </div>
          <button class="soft-chip soft-chip-button" data-route="archive" type="button">Архив</button>
        </div>
        ${renderArchiveRows(data.recent_archive)}
      </article>
      <article class="surface">
        <div class="surface-head">
          <div>
            <p class="eyebrow">Качество</p>
            <h3>Сигналы по сервису</h3>
          </div>
          <button class="soft-chip soft-chip-button" data-route="analytics" type="button">Аналитика</button>
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
  const categories = buildArchiveCategories(data.items);
  const items = applyArchiveFilters(data.items, filters);
  const selectedCategory = findArchiveCategory(categories, filters.category ?? "");
  const pickerOpen = Boolean(filters.pickerOpen);
  const archiveBody =
    data.items.length === 0 && !filters.search && !filters.category
      ? renderEmptyBlock(
          "Архив пока пуст.",
          "Закрытые дела появятся здесь автоматически и будут собраны по темам.",
        )
      : renderArchiveRows(items, true);

  return `
    <section class="surface surface-roomy">
      <div class="surface-head">
        <div>
          <p class="eyebrow">Архив</p>
          <h2>Закрытые и обработанные</h2>
          <p class="subtitle">История по делам, темам и завершённым контекстам без лишнего шума.</p>
        </div>
        <div class="archive-summary">
          <span class="soft-chip">${escapeHtml(String(items.length))} найдено</span>
          ${
            selectedCategory
              ? `<span class="soft-chip">${escapeHtml(selectedCategory.title)}</span>`
              : `<span class="soft-chip">Все темы</span>`
          }
        </div>
      </div>
      <div class="archive-toolbar">
        <div class="archive-search-block">
          ${renderSearchRow("archive-search", "Поиск по номеру, теме или коду", filters.search ?? "")}
        </div>
        <div class="archive-filter-row">
          <button
            class="filter-chip ${!selectedCategory ? "is-active" : ""}"
            data-archive-filter="all"
            type="button"
          >
            Все темы
          </button>
          <button
            class="filter-chip filter-chip-quiet ${pickerOpen ? "is-active" : ""}"
            data-archive-filter="picker"
            type="button"
          >
            ${selectedCategory ? "Сменить тему" : "Выбрать тему"}
          </button>
          ${
            selectedCategory
              ? `
                <button
                  class="filter-chip filter-chip-selected"
                  data-archive-filter="picker"
                  type="button"
                >
                  ${escapeHtml(selectedCategory.title)}
                  ${selectedCategory.code ? `<span>${escapeHtml(selectedCategory.code)}</span>` : ""}
                </button>
              `
              : ""
          }
        </div>
      </div>
      ${
        pickerOpen
          ? renderArchiveCategoryPicker(categories, selectedCategory)
          : ""
      }
      ${archiveBody}
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
        <div class="utility-actions utility-actions-end">
          <span class="utility-label">Выгрузка</span>
          <button class="action action-subtle" data-export-analytics="html">HTML</button>
          <button class="action action-subtle" data-export-analytics="csv">CSV</button>
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
            operators.length
              ? operators
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
            <p class="eyebrow">AI settings</p>
            <h2>Safe AI controls</h2>
          </div>
        </div>
        ${renderAISettingsForm(aiSettings)}
      </article>
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
          "AI summaries",
          "Generate operator-facing ticket summaries.",
          settings.ai_summaries_enabled !== false,
        )}
        ${renderSettingsToggle(
          "ai_macro_suggestions_enabled",
          "Macro suggestions",
          "Suggest existing macros from ticket context.",
          settings.ai_macro_suggestions_enabled !== false,
        )}
        ${renderSettingsToggle(
          "ai_reply_drafts_enabled",
          "Reply drafts",
          "Prepare drafts that operators must review.",
          settings.ai_reply_drafts_enabled !== false,
        )}
        ${renderSettingsToggle(
          "ai_category_prediction_enabled",
          "Category prediction",
          "Predict ticket category from safe intake context.",
          settings.ai_category_prediction_enabled !== false,
        )}
      </div>

      <label class="settings-field">
        <span>Default model id</span>
        <input
          name="default_model_id"
          type="text"
          value="${escapeAttribute(settings.default_model_id || "")}"
          placeholder="Use env/provider default"
          autocomplete="off"
        />
      </label>

      <div class="settings-row">
        <label class="settings-field">
          <span>Max history messages</span>
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
          <span>Reply tone</span>
          <select name="reply_draft_tone">
            ${["polite", "friendly", "formal"]
              .map(
                (value) => `
                  <option value="${value}" ${tone === value ? "selected" : ""}>
                    ${value}
                  </option>
                `,
              )
              .join("")}
          </select>
        </label>
      </div>

      <div class="settings-review-note">
        <strong>Operator review required</strong>
        <span>AI output remains draft-only. Provider secrets and API keys are never shown here.</span>
      </div>

      <div class="inline-actions">
        <button class="action action-primary" type="submit">Save settings</button>
        <button class="action action-subtle" data-ai-settings-cancel type="button">Cancel</button>
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

export function renderTicketWorkspace(data, replyDraftState = null) {
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
        <div class="detail-actions ticket-action-bar">
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
      </div>

      <div class="ticket-workspace-grid">
        <article class="subsurface">
          <div class="subsurface-head">
            <h3>Карточка</h3>
            <span class="soft-chip">Карточка</span>
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
                  <button class="action action-subtle" type="submit">Назначить</button>
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

function renderDashboardBucketSection(title, bucketKeys, buckets) {
  const keys = Array.isArray(bucketKeys) ? bucketKeys : [];
  return `
    <article class="dashboard-section">
      <div class="dashboard-section-head">
        <h3>${escapeHtml(title)}</h3>
      </div>
      <div class="dashboard-bucket-stack">
        ${
          keys
            .map((key) => buckets[key])
            .filter(Boolean)
            .map(renderAttentionBucket)
            .join("") || renderDashboardEmptyState("Нет данных для этого блока.")
        }
      </div>
    </article>
  `;
}

function renderAttentionBucket(bucket) {
  const route = bucket.route || "queue";
  const severity = bucket.severity === "critical" || bucket.severity === "warning"
    ? bucket.severity
    : "neutral";
  return `
    <article
      class="attention-bucket ${severity === "critical" ? "is-critical" : ""} ${severity === "warning" ? "is-warning" : ""}"
      data-route="${escapeAttribute(route)}"
    >
      <div class="attention-bucket-head">
        <div>
          <span class="attention-count">${escapeHtml(String(bucket.count ?? 0))}</span>
          <h4>${escapeHtml(bucket.label || bucket.key || "Bucket")}</h4>
        </div>
        <span class="row-hint">Открыть</span>
      </div>
      ${
        bucket.unavailable_reason
          ? `<p class="dashboard-bucket-note">${escapeHtml(bucket.unavailable_reason)}</p>`
          : ""
      }
      ${
        Array.isArray(bucket.tickets) && bucket.tickets.length
          ? renderTicketPreviewList(bucket.tickets)
          : renderDashboardEmptyState(bucket.empty_label || "Сейчас пусто.")
      }
    </article>
  `;
}

function renderTicketPreviewList(items) {
  return `
    <div class="ticket-preview-list">
      ${items.map(renderTicketPreviewCard).join("")}
    </div>
  `;
}

function renderTicketPreviewCard(item) {
  const sentiment = item.sentiment?.value ? sentimentLabel(item.sentiment.value) : "";
  const slaState = item.sla_state?.status ? `SLA: ${item.sla_state.status}` : "";
  const assignedOperator = item.assigned_operator?.name || "";
  return `
    <article class="ticket-preview-card" data-open-ticket="${escapeAttribute(item.public_id)}">
      <div class="ticket-preview-main">
        <p class="ticket-number">${escapeHtml(item.public_number || item.public_id)}</p>
        <h4>${escapeHtml(item.subject || "Без темы")}</h4>
        <div class="meta-row meta-row-wrap">
          <span class="status-chip">${statusLabel(item.status)}</span>
          <span class="soft-chip">${item.category || item.category_title ? escapeHtml(item.category || item.category_title) : "Без темы"}</span>
          ${slaState ? `<span class="soft-chip">${escapeHtml(slaState)}</span>` : ""}
          ${sentiment ? `<span class="soft-chip">${escapeHtml(sentiment)}</span>` : ""}
        </div>
      </div>
      <div class="ticket-preview-meta">
        <span>${formatDateTime(item.last_activity_at)}</span>
        ${assignedOperator ? `<span>${escapeHtml(assignedOperator)}</span>` : ""}
      </div>
    </article>
  `;
}

function renderDashboardEmptyState(text) {
  return `<div class="dashboard-empty-state">${escapeHtml(text)}</div>`;
}

function renderTicketPreviewColumn(title, subtitle, items, route) {
  return `
    <article class="surface surface-compact">
      <div class="surface-head">
        <div>
          <p class="eyebrow">${escapeHtml(title)}</p>
          <h3>${escapeHtml(subtitle)}</h3>
        </div>
        <button class="soft-chip soft-chip-button" data-route="${route}" type="button">Открыть раздел</button>
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
                <span class="row-hint">Открыть</span>
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
    return renderEmptyBlock(
      "Ничего не найдено.",
      "Попробуйте убрать тему или изменить поисковый запрос.",
    );
  }

  return `
    <div class="archive-list">
      ${items
        .map(
          (item) => `
            <article class="archive-row" data-open-ticket="${item.public_id}">
              <div class="archive-row-main">
                <div class="ticket-copy">
                  <p class="ticket-number">${escapeHtml(item.public_number)}</p>
                  <h3>${escapeHtml(item.mini_title)}</h3>
                  <p class="subtitle">${escapeHtml(buildArchivePreview(item))}</p>
                </div>
                <div class="archive-meta">
                  <div class="archive-meta-row">
                    <span class="soft-chip">${escapeHtml(item.category_title || "Без темы")}</span>
                    ${
                      item.category_code
                        ? `<span class="soft-chip soft-chip-code">${escapeHtml(item.category_code)}</span>`
                        : ""
                    }
                  </div>
                  <p class="archive-date">
                    ${item.closed_at ? formatDateTime(item.closed_at) : formatDateTime(item.created_at)}
                  </p>
                </div>
              </div>
              ${full ? `<span class="row-hint">Открыть</span>` : ""}
            </article>
          `,
        )
        .join("")}
    </div>
  `;
}

function renderArchiveCategoryPicker(categories, selectedCategory) {
  return `
    <section class="archive-picker">
      <div class="surface-head archive-picker-head">
        <div>
          <p class="eyebrow">Тема</p>
          <h3>Выберите тему</h3>
          <p class="subtitle">Фильтр вернёт вас к списку и оставит архив в текущем контексте.</p>
        </div>
        <button class="action action-subtle" data-archive-filter="close-picker" type="button">Закрыть</button>
      </div>
      <div class="archive-picker-grid">
        <button
          class="archive-picker-card ${!selectedCategory ? "is-active" : ""}"
          data-archive-category=""
          type="button"
        >
          <strong>Все темы</strong>
          <span>Показать весь архив без сужения.</span>
        </button>
        ${categories
          .map(
            (category) => `
              <button
                class="archive-picker-card ${selectedCategory?.value === category.value ? "is-active" : ""}"
                data-archive-category="${escapeAttribute(category.value)}"
                type="button"
              >
                <strong>${escapeHtml(category.title)}</strong>
                <span>
                  ${category.code ? `${escapeHtml(category.code)} · ` : ""}${escapeHtml(String(category.count))} в архиве
                </span>
              </button>
            `,
          )
          .join("")}
      </div>
    </section>
  `;
}

function buildArchivePreview(item) {
  const parts = [];
  if (item.category_title) {
    parts.push(item.category_title);
  }
  if (item.category_code) {
    parts.push(item.category_code);
  }
  const dateLabel = item.closed_at ? "Закрыта" : "Создана";
  parts.push(`${dateLabel} ${item.closed_at ? formatDateTime(item.closed_at) : formatDateTime(item.created_at)}`);
  return parts.join(" · ");
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

function renderTicketTimeline(timeline) {
  const items = Array.isArray(timeline?.items) ? timeline.items : [];
  const warning =
    typeof timeline?.warning === "string" && timeline.warning.trim() ? timeline.warning : "";
  if (warning) {
    return `<div class="ai-warning">${escapeHtml(warning)}</div>`;
  }
  if (!items.length) {
    return renderInlineEmpty("No ticket history yet.");
  }
  return `
    <div class="ticket-timeline">
      ${items.map(renderTicketTimelineItem).join("")}
    </div>
  `;
}

function renderTicketTimelineItem(item) {
  const modifier = timelineTypeModifier(item?.type);
  return `
    <article class="timeline-item ${modifier}">
      <span class="timeline-marker" aria-hidden="true"></span>
      <div class="timeline-content">
        <div class="timeline-meta">
          <span>${formatDateTime(item?.created_at)}</span>
          ${
            item?.actor_label
              ? `<span>${escapeHtml(item.actor_label)}</span>`
              : ""
          }
        </div>
        <h4>${escapeHtml(item?.title || "Ticket event")}</h4>
        <p>${escapeHtml(item?.description || "Event recorded.")}</p>
      </div>
    </article>
  `;
}

function timelineTypeModifier(type) {
  if (type === "ai_summary_generated" || type === "ai_reply_draft_generated") {
    return "is-ai";
  }
  if (type === "sla_warning" || type === "sla_breached") {
    return "is-sla";
  }
  if (type === "ticket_assigned" || type === "ticket_unassigned") {
    return "is-assignment";
  }
  if (type === "message_received" || type === "operator_reply") {
    return "is-message";
  }
  if (type === "internal_note_added") {
    return "is-note";
  }
  if (type === "ticket_closed" || type === "ticket_reopened") {
    return "is-close";
  }
  return "";
}

function renderTicketAiCard(ai) {
  const status = normalizeSummaryStatus(ai?.summary_status);
  const statusText = summaryStatusLabel(status);
  const refreshLabel = status === "missing" ? "Generate summary" : "Refresh summary";

  if (!ai) {
    return `
      <article class="subsurface ai-card is-missing">
        <div class="subsurface-head">
          <div>
            <h3>AI-сводка</h3>
            <p class="subtitle">AI-контекст не вернулся от backend.</p>
          </div>
          <span class="soft-chip">Missing</span>
        </div>
        <div class="ai-section">
          <p class="empty-inline">Можно продолжать работу по истории сообщений и заметкам.</p>
        </div>
        <button class="action action-primary" data-ticket-ai-refresh type="button">Generate summary</button>
      </article>
    `;
  }

  const unavailable = ai.available === false;
  return `
    <article class="subsurface ai-card is-${status}">
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

function renderAiReplyCard(replyDraftState) {
  const payload = replyDraftState?.payload ?? null;
  const isLoading = Boolean(replyDraftState?.loading);
  return `
    <article class="subsurface ai-reply-card">
      <div class="subsurface-head">
        <div>
          <h3>AI reply draft</h3>
          <p class="subtitle">Черновик только для проверки оператором. Автоотправки нет.</p>
        </div>
        <button
          class="action action-primary"
          data-ticket-ai-reply-draft
          type="button"
          ${isLoading ? "disabled" : ""}
        >
          ${isLoading ? "Generating..." : "Generate AI reply"}
        </button>
      </div>
      ${renderAiReplyDraft(payload, isLoading)}
    </article>
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
      </div>
    `;
  }
  return `
    <div class="ai-reply-draft">
      <p>${escapeHtml(payload.reply_text || "Черновик пуст.")}</p>
      ${
        payload.reply_text
          ? `<button class="action action-subtle copy-draft-button" data-copy-draft type="button">Copy draft</button>`
          : ""
      }
    </div>
    <div class="ai-reply-meta">
      ${payload.tone ? `<span class="soft-chip">Tone: ${escapeHtml(payload.tone)}</span>` : ""}
      ${
        payload.confidence !== null && payload.confidence !== undefined
          ? `<span class="soft-chip">Confidence: ${escapeHtml(formatConfidence(payload.confidence))}</span>`
          : ""
      }
      ${payload.model_id ? `<span class="soft-chip">Model: ${escapeHtml(payload.model_id)}</span>` : ""}
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
      <strong>Missing information</strong>
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

function renderMacroList(macros, suggestions) {
  const suggestedIds = new Set(suggestions.map((item) => item.macro_id).filter(Boolean));
  const remainingMacros = macros.filter((macro) => !suggestedIds.has(macro.id));
  if (!macros.length && !suggestions.length) {
    return renderInlineEmpty("Макросы ещё не созданы.");
  }

  return `
    <section class="macro-section">
      <div class="macro-section-head">
        <h5>AI recommends</h5>
        <span class="soft-chip">${escapeHtml(String(suggestions.length))}</span>
      </div>
      ${
        suggestions.length
          ? suggestions.map(renderMacroSuggestion).join("")
          : renderInlineEmpty("Точных AI-рекомендаций сейчас нет.")
      }
    </section>
    <section class="macro-section">
      <div class="macro-section-head">
        <h5>All macros</h5>
        <span class="soft-chip">${escapeHtml(String(remainingMacros.length))}</span>
      </div>
      ${
        remainingMacros.length
          ? remainingMacros
              .slice(0, 8)
              .map(
                (macro) => `
                  <button class="macro-button" data-apply-macro="${macro.id}">
                    <strong>${escapeHtml(macro.title)}</strong>
                    <span>${escapeHtml(macro.body)}</span>
                  </button>
                `,
              )
              .join("")
          : renderInlineEmpty("Все подходящие макросы уже показаны в рекомендациях.")
      }
    </section>
  `;
}

function renderMacroSuggestion(suggestion) {
  return `
    <button class="macro-button macro-suggestion is-suggested" data-apply-macro="${suggestion.macro_id}">
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
    fresh: "Fresh",
    stale: "Stale",
    missing: "Missing",
  }[status];
}

function confidenceLabel(confidence) {
  return {
    high: "high confidence",
    medium: "medium confidence",
    low: "low confidence",
    none: "no confidence",
  }[confidence] ?? confidence;
}
