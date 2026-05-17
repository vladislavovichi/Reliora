import {
  renderBar,
  renderInlineEmpty,
  renderMetric,
} from "../render-utils.js";

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
