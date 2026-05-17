import { escapeHtml } from "../render-utils.js";

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
          <span class="nav-dot" aria-hidden="true"></span>
          <span>${ROUTE_LABELS[route]}</span>
        </button>
      `,
    )
    .join("");
}

export function renderAccessDenied(message) {
  return `
    <section class="state-panel premium-state">
      <div class="state-orb" aria-hidden="true"></div>
      <p class="eyebrow">Рабочее место</p>
      <h2>Доступ закрыт</h2>
      <p class="subtitle">${escapeHtml(message)}</p>
    </section>
  `;
}

export function renderInitDataMissing(copy) {
  return `
    <section class="state-panel premium-state">
      <div class="state-orb" aria-hidden="true"></div>
      <div class="state-badge-row">
        <p class="eyebrow">Рабочее место</p>
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
        <p>Откройте приложение через кнопку меню «Рабочее место» в чате с ботом.</p>
        <p>Если проблема повторяется, закройте окно и запустите рабочее место заново.</p>
      </div>
    </section>
  `;
}

export function renderError(message) {
  return `
    <section class="state-panel premium-state state-error">
      <div class="state-orb" aria-hidden="true"></div>
      <p class="eyebrow">Ошибка</p>
      <h2>Не удалось загрузить данные</h2>
      <p class="subtitle">${escapeHtml(message)}</p>
    </section>
  `;
}

export function renderLoading() {
  return `
    <section class="loading-state premium-loading">
      <div class="loading-stack">
        <div class="loading-kicker"></div>
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
