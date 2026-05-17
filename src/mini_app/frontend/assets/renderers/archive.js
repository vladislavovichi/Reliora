import {
  applyArchiveFilters,
  buildArchiveCategories,
  escapeAttribute,
  escapeHtml,
  findArchiveCategory,
  formatDateTime,
  renderEmptyBlock,
  renderInlineEmpty,
  renderSearchRow,
} from "../render-utils.js";

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

export function renderArchiveRows(items, full = false) {
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
            <article class="archive-row" data-open-ticket="${escapeAttribute(item.public_id)}">
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
