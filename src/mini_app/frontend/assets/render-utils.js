const STATUS_LABELS = {
  new: "Новая",
  queued: "В очереди",
  assigned: "В работе",
  escalated: "Эскалация",
  closed: "Закрыта",
};

const PRIORITY_LABELS = {
  low: "Низкий",
  normal: "Нормальный",
  high: "Высокий",
  urgent: "Срочный",
};

export function renderMetric(label, value) {
  return `
    <div class="metric">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(String(value))}</strong>
    </div>
  `;
}

export function renderBar(label, value, maxValue, valueLabel) {
  const safeMax = Math.max(maxValue || 0, 1);
  const width = Math.max(Math.min((value / safeMax) * 100, 100), 4);
  return `
    <div class="bar-row">
      <div class="bar-head">
        <span>${escapeHtml(label)}</span>
        <strong>${escapeHtml(valueLabel ?? String(value))}</strong>
      </div>
      <div class="bar-track"><span style="width:${width}%"></span></div>
    </div>
  `;
}

export function renderFact(label, value) {
  return `
    <div class="fact-row">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
    </div>
  `;
}

export function renderSearchRow(id, placeholder, value) {
  return `
    <label class="search-field">
      <span class="sr-only">Поиск</span>
      <input id="${id}" type="search" value="${escapeAttribute(value)}" placeholder="${escapeAttribute(placeholder)}" />
    </label>
  `;
}

export function renderEmptyBlock(title, text) {
  return `
    <section class="empty-state">
      <p class="eyebrow">Спокойно</p>
      <h3>${escapeHtml(title)}</h3>
      <p class="subtitle">${escapeHtml(text)}</p>
    </section>
  `;
}

export function renderInlineEmpty(text) {
  return `<p class="empty-inline">${escapeHtml(text)}</p>`;
}

export function applyTicketFilters(items, filters) {
  return items.filter((item) => matchesTicketSearch(item, filters.search ?? ""));
}

export function applyArchiveFilters(items, filters) {
  const selectedCategory = normalizeSearch(filters.category ?? "");
  return items.filter((item) => {
    const matchesSearch = matchesArchiveSearch(item, filters.search ?? "");
    const matchesCategory =
      !selectedCategory ||
      normalizeSearch(item.category_title).includes(selectedCategory) ||
      normalizeSearch(item.category_code).includes(selectedCategory);
    return matchesSearch && matchesCategory;
  });
}

export function buildArchiveCategories(items) {
  const categories = new Map();
  for (const item of items) {
    const title = typeof item.category_title === "string" ? item.category_title.trim() : "";
    const code = typeof item.category_code === "string" ? item.category_code.trim() : "";
    const key = `${title.toLowerCase()}::${code.toLowerCase()}`;
    if (!title && !code) {
      continue;
    }
    if (!categories.has(key)) {
      categories.set(key, {
        value: title || code,
        title: title || "Без названия",
        code: code || null,
        count: 0,
      });
    }
    categories.get(key).count += 1;
  }

  return Array.from(categories.values()).sort((left, right) => {
    if (right.count !== left.count) {
      return right.count - left.count;
    }
    return left.title.localeCompare(right.title, "ru");
  });
}

export function findArchiveCategory(categories, selectedValue) {
  const normalizedSelectedValue = normalizeSearch(selectedValue);
  if (!normalizedSelectedValue) {
    return null;
  }
  return (
    categories.find(
      (category) =>
        normalizeSearch(category.value) === normalizedSelectedValue ||
        normalizeSearch(category.title) === normalizedSelectedValue ||
        normalizeSearch(category.code) === normalizedSelectedValue,
    ) ?? null
  );
}

export function statusLabel(status) {
  return STATUS_LABELS[status] ?? status;
}

export function priorityLabel(priority) {
  return PRIORITY_LABELS[priority] ?? priority;
}

export function sentimentLabel(sentiment) {
  return {
    calm: "Спокойный тон",
    frustrated: "Недовольство",
    escalation_risk: "Риск эскалации",
    positive: "Позитивный сигнал",
    neutral: "Нейтральный сигнал",
    negative: "Негативный сигнал",
  }[sentiment] ?? sentiment;
}

export function senderLabel(senderType, name) {
  if (senderType === "operator" || senderType === "internal") {
    return name ?? "Оператор";
  }
  return "Клиент";
}

export function formatDateTime(value) {
  if (!value) {
    return "—";
  }

  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

export function formatDuration(seconds) {
  if (!seconds && seconds !== 0) {
    return "—";
  }
  if (seconds < 60) {
    return `${seconds} сек`;
  }
  if (seconds < 3600) {
    return `${Math.round(seconds / 60)} мин`;
  }
  return `${Math.round(seconds / 3600)} ч`;
}

export function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

export function escapeAttribute(value) {
  return escapeHtml(value ?? "");
}

function matchesTicketSearch(item, search) {
  const normalized = normalizeSearch(search);
  if (!normalized) {
    return true;
  }

  return [item.public_number, item.subject, item.mini_title]
    .filter(Boolean)
    .some((value) => normalizeSearch(value).includes(normalized));
}

function matchesArchiveSearch(item, search) {
  const normalized = normalizeSearch(search);
  if (!normalized) {
    return true;
  }

  return [
    item.public_number,
    item.subject,
    item.mini_title,
    item.category_title,
    item.category_code,
  ]
    .filter(Boolean)
    .some((value) => normalizeSearch(value).includes(normalized));
}

function normalizeSearch(value) {
  if (typeof value !== "string") {
    return "";
  }
  return value.trim().toLowerCase();
}
