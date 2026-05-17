import {
  escapeAttribute,
  escapeHtml,
  formatDateTime,
  formatDuration,
  priorityLabel,
  renderBar,
  renderFact,
  renderInlineEmpty,
  renderMetric,
  sentimentLabel,
  statusLabel,
} from "../render-utils.js";
import { renderArchiveRows } from "./archive.js";

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
    <section class="hero-grid dashboard-hero-grid">
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
        <div class="hero-signal-strip">
          <span>Очередь <strong>${escapeHtml(String(snapshot.queued_tickets_count))}</strong></span>
          <span>Назначено <strong>${escapeHtml(String(snapshot.assigned_tickets_count))}</strong></span>
          <span>SLA риск <strong>${escapeHtml(String(snapshot.first_response_breach_count + snapshot.resolution_breach_count))}</strong></span>
        </div>
        <div class="inline-actions">
          <button class="action action-primary" data-action="take-next">Взять следующую</button>
        </div>
        <p class="hero-note">Если нужен конкретный кейс, откройте очередь или свои заявки через навигацию.</p>
      </article>
      <article class="hero-card hero-card-secondary executive-card">
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
        ${renderDashboardBucketSection("Требует внимания", sections.needs_attention, buckets)}
        ${renderDashboardBucketSection("Моя работа", sections.my_work, buckets)}
        ${renderDashboardBucketSection("Очередь", sections.queue, buckets)}
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
          <h4>${escapeHtml(bucket.label || bucket.key || "Блок")}</h4>
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
  const slaState = item.sla_state?.status ? `SLA: ${slaStatusLabel(item.sla_state.status)}` : "";
  const assignedOperator = item.assigned_operator?.name || "";
  return `
    <article class="ticket-preview-card priority-${escapeAttribute(item.priority || "normal")}" data-open-ticket="${escapeAttribute(item.public_id)}">
      <div class="ticket-preview-main">
        <p class="ticket-number">${escapeHtml(item.public_number || item.public_id)}</p>
        <h4>${escapeHtml(item.subject || "Без темы")}</h4>
        <div class="meta-row meta-row-wrap">
          <span class="status-chip status-${escapeAttribute(item.status)}">${statusLabel(item.status)}</span>
          ${item.priority ? `<span class="priority-pill priority-${escapeAttribute(item.priority)}">${priorityLabel(item.priority)}</span>` : ""}
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

function slaStatusLabel(status) {
  return {
    ok: "в норме",
    at_risk: "риск",
    breached: "нарушен",
    missing: "нет данных",
  }[status] ?? status;
}
