import { MiniAppRequestError, createMiniAppApi } from "./api.js";
import {
  buildNavigation,
  renderAccessDenied,
  renderAdmin,
  renderAnalytics,
  renderArchive,
  renderDashboard,
  renderError,
  renderInitDataMissing,
  renderLoading,
  renderMyTickets,
  renderQueue,
  renderTicketWorkspace,
} from "./renderers.js";
import {
  buildLaunchFailureCopy,
  clearPersistedLaunchContext,
  createTelegramLaunchContext,
} from "./telegram.js";

const telegram = window.Telegram?.WebApp ?? null;
const content = document.getElementById("content");
const navStrip = document.getElementById("nav-strip");
const identityName = document.getElementById("identity-name");
const identityRole = document.getElementById("identity-role");
const appNotice = document.getElementById("app-notice");

const state = {
  api: null,
  launch: null,
  session: null,
  currentRoute: "dashboard",
  currentTicketId: null,
  analyticsWindow: "7d",
  filters: {
    queue: { search: "" },
    mine: { search: "" },
    archive: { search: "", category: "", pickerOpen: false },
  },
  cache: {
    dashboard: null,
    queue: null,
    mine: null,
    archive: null,
    analytics: {},
    admin: null,
    tickets: {},
  },
  aiReplyDrafts: {},
  lastInvite: null,
};

let noticeTimeoutId = 0;

async function boot() {
  state.launch = await resolveLaunchContext();
  state.api = createMiniAppApi(state.launch);

  if (!state.api.hasInitData()) {
    content.innerHTML = renderInitDataMissing(buildLaunchFailureCopy(state.launch));
    return;
  }

  try {
    state.session = await getSessionWithRetry();
    updateIdentity();
    syncRoute();
    bindGlobalEvents();
    await renderRoute();
  } catch (error) {
    renderBootFailure(error);
  }
}

function renderBootFailure(error) {
  if (error instanceof MiniAppRequestError) {
    if (error.status === 401) {
      clearStaleLaunchState(error);
      content.innerHTML = renderInitDataMissing(buildLaunchFailureCopy(state.launch, error));
      return;
    }
    if (error.status === 403) {
      content.innerHTML = renderAccessDenied(resolveErrorMessage(error));
      return;
    }
  }

  content.innerHTML = renderError(resolveErrorMessage(error));
}

function updateIdentity() {
  identityName.textContent = state.session.user.display_name;
  identityRole.textContent =
    state.session.access.role === "super_admin" ? "Суперадминистратор" : "Оператор";
  navStrip.innerHTML = buildNavigation(state.session.access.role, state.currentRoute);
}

function syncRoute() {
  const hash = window.location.hash.replace(/^#/, "");
  if (hash.startsWith("ticket/")) {
    state.currentRoute = "ticket";
    state.currentTicketId = hash.split("/")[1] ?? null;
    navStrip.innerHTML = buildNavigation(state.session.access.role, "");
    return;
  }

  state.currentRoute = hash || "dashboard";
  state.currentTicketId = null;
  navStrip.innerHTML = buildNavigation(state.session.access.role, state.currentRoute);
}

async function renderRoute() {
  content.innerHTML = renderLoading();

  try {
    if (state.session.access.role === "user") {
      content.innerHTML = renderAccessDenied(
        "Рабочее место доступно только операторам и суперадминистраторам.",
      );
      return;
    }

    if (state.currentRoute === "dashboard") {
      content.innerHTML = renderDashboard(await loadDashboard());
      return;
    }

    if (state.currentRoute === "queue") {
      content.innerHTML = renderQueue(await loadQueue(), state.filters.queue);
      return;
    }

    if (state.currentRoute === "mine") {
      content.innerHTML = renderMyTickets(await loadMyTickets(), state.filters.mine);
      return;
    }

    if (state.currentRoute === "archive") {
      content.innerHTML = renderArchive(await loadArchive(), state.filters.archive);
      return;
    }

    if (state.currentRoute === "analytics") {
      content.innerHTML = renderAnalytics(
        await loadAnalytics(state.analyticsWindow),
        state.analyticsWindow,
      );
      return;
    }

    if (state.currentRoute === "admin") {
      content.innerHTML = renderAdmin(await loadAdmin(), state.lastInvite);
      return;
    }

    if (state.currentRoute === "ticket" && state.currentTicketId) {
      content.innerHTML = renderTicketWorkspace(
        await loadTicket(state.currentTicketId),
        state.aiReplyDrafts[state.currentTicketId] ?? null,
      );
      return;
    }

    content.innerHTML = renderError("Маршрут не распознан.");
  } catch (error) {
    renderRouteFailure(error);
  }
}

function renderRouteFailure(error) {
  if (error instanceof MiniAppRequestError && error.status === 401) {
    clearStaleLaunchState(error);
    content.innerHTML = renderInitDataMissing(buildLaunchFailureCopy(state.launch, error));
    return;
  }
  if (error instanceof MiniAppRequestError && error.status === 403) {
    content.innerHTML = renderAccessDenied(resolveErrorMessage(error));
    return;
  }
  content.innerHTML = renderError(resolveErrorMessage(error));
}

function bindGlobalEvents() {
  window.addEventListener("hashchange", async () => {
    syncRoute();
    await renderRoute();
  });

  navStrip.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-route]");
    if (!button) {
      return;
    }
    window.location.hash = button.dataset.route;
  });

  content.addEventListener("click", async (event) => {
    const routeButton = event.target.closest("[data-route]");
    if (routeButton) {
      window.location.hash = routeButton.dataset.route;
      return;
    }

    const openButton = event.target.closest("[data-open-ticket]");
    if (openButton) {
      window.location.hash = `ticket/${openButton.dataset.openTicket}`;
      return;
    }

    const archiveFilterButton = event.target.closest("[data-archive-filter]");
    if (archiveFilterButton) {
      const archiveFilterAction = archiveFilterButton.dataset.archiveFilter;
      if (archiveFilterAction === "all") {
        state.filters.archive.category = "";
        state.filters.archive.pickerOpen = false;
      }
      if (archiveFilterAction === "picker") {
        state.filters.archive.pickerOpen = true;
      }
      if (archiveFilterAction === "close-picker") {
        state.filters.archive.pickerOpen = false;
      }
      content.innerHTML = renderArchive(await loadArchive(), state.filters.archive);
      return;
    }

    const archiveCategoryButton = event.target.closest("[data-archive-category]");
    if (archiveCategoryButton) {
      state.filters.archive.category = archiveCategoryButton.dataset.archiveCategory ?? "";
      state.filters.archive.pickerOpen = false;
      content.innerHTML = renderArchive(await loadArchive(), state.filters.archive);
      return;
    }

    const takeButton = event.target.closest("[data-take-ticket]");
    if (takeButton) {
      await runMutation(async () => {
        await state.api.takeTicket(takeButton.dataset.takeTicket);
        invalidateTicketData(takeButton.dataset.takeTicket);
        window.location.hash = `ticket/${takeButton.dataset.takeTicket}`;
      });
      return;
    }

    const ticketAction = event.target.closest("[data-ticket-action]");
    if (ticketAction && state.currentTicketId) {
      const action = ticketAction.dataset.ticketAction;
      await runMutation(async () => {
        if (action === "take") {
          await state.api.takeTicket(state.currentTicketId);
        } else if (action === "close") {
          await state.api.closeTicket(state.currentTicketId);
        } else if (action === "escalate") {
          await state.api.escalateTicket(state.currentTicketId);
        }
        invalidateTicketData(state.currentTicketId);
      });
      await renderRoute();
      return;
    }

    const takeNextButton = event.target.closest("[data-action='take-next']");
    if (takeNextButton) {
      await runMutation(async () => {
        const result = await state.api.takeNext();
        invalidateTicketCollections();
        window.location.hash = `ticket/${result.ticket.public_id}`;
      });
      return;
    }

    const createInviteButton = event.target.closest("[data-action='create-invite']");
    if (createInviteButton) {
      await runMutation(async () => {
        const result = await state.api.createInvite();
        state.lastInvite = result.invite;
        state.cache.admin = null;
      });
      await renderRoute();
      showNotice("Инвайт создан.", "success");
      return;
    }

    const copyButton = event.target.closest("[data-copy]");
    if (copyButton) {
      await handleCopy(copyButton.dataset.copy ?? "");
      return;
    }

    const copyDraftButton = event.target.closest("[data-copy-draft]");
    if (copyDraftButton && state.currentTicketId) {
      const draftText = state.aiReplyDrafts[state.currentTicketId]?.payload?.reply_text ?? "";
      await handleCopy(draftText, "Черновик скопирован.");
      return;
    }

    const macroButton = event.target.closest("[data-apply-macro]");
    if (macroButton && state.currentTicketId) {
      await runMutation(async () => {
        await state.api.applyMacro(state.currentTicketId, macroButton.dataset.applyMacro);
        invalidateTicketData(state.currentTicketId);
      });
      await renderRoute();
      return;
    }

    const ticketAiRefreshButton = event.target.closest("[data-ticket-ai-refresh]");
    if (ticketAiRefreshButton && state.currentTicketId) {
      let refreshed = false;
      await runMutation(async () => {
        await state.api.refreshTicketAi(state.currentTicketId);
        invalidateTicketData(state.currentTicketId);
        await renderRoute();
        refreshed = true;
      });
      if (refreshed) {
        showNotice("AI summary updated.", "success");
      }
      return;
    }

    const ticketAiReplyDraftButton = event.target.closest("[data-ticket-ai-reply-draft]");
    if (ticketAiReplyDraftButton && state.currentTicketId) {
      const ticketId = state.currentTicketId;
      state.aiReplyDrafts[ticketId] = { loading: true, payload: null };
      await renderRoute();
      let generated = false;
      await runMutation(async () => {
        const payload = await state.api.generateTicketReplyDraft(ticketId);
        state.aiReplyDrafts[ticketId] = { loading: false, payload };
        generated = true;
      });
      if (!generated) {
        state.aiReplyDrafts[ticketId] = { loading: false, payload: null };
      }
      await renderRoute();
      if (generated) {
        showNotice("AI reply draft generated.", "success");
      }
      return;
    }

    const ticketExportButton = event.target.closest("[data-ticket-export]");
    if (ticketExportButton && state.currentTicketId) {
      await runMutation(() =>
        state.api.downloadTicket(state.currentTicketId, ticketExportButton.dataset.ticketExport),
      );
      showNotice("Файл готов к загрузке.", "success");
      return;
    }

    const analyticsExportButton = event.target.closest("[data-export-analytics]");
    if (analyticsExportButton) {
      await runMutation(() =>
        state.api.downloadAnalytics(
          state.analyticsWindow,
          "overview",
          analyticsExportButton.dataset.exportAnalytics,
        ),
      );
      showNotice("Выгрузка подготовлена.", "success");
      return;
    }

    const windowButton = event.target.closest("[data-window]");
    if (windowButton) {
      state.analyticsWindow = windowButton.dataset.window;
      await renderRoute();
    }
  });

  content.addEventListener("input", async (event) => {
    if (event.target.id === "queue-search") {
      state.filters.queue.search = event.target.value;
      content.innerHTML = renderQueue(await loadQueue(), state.filters.queue);
    }

    if (event.target.id === "mine-search") {
      state.filters.mine.search = event.target.value;
      content.innerHTML = renderMyTickets(await loadMyTickets(), state.filters.mine);
    }

    if (event.target.id === "archive-search") {
      state.filters.archive.search = event.target.value;
      content.innerHTML = renderArchive(await loadArchive(), state.filters.archive);
    }
  });

  content.addEventListener("submit", async (event) => {
    event.preventDefault();

    if (event.target.id === "note-form" && state.currentTicketId) {
      const noteField = document.getElementById("note-text");
      if (!noteField) {
        return;
      }
      await runMutation(async () => {
        await state.api.addTicketNote(state.currentTicketId, noteField.value);
        invalidateTicketData(state.currentTicketId);
      });
      noteField.value = "";
      await renderRoute();
      showNotice("Заметка сохранена.", "success");
    }

    if (event.target.id === "assign-form" && state.currentTicketId) {
      const select = document.getElementById("assign-operator");
      const option = select?.selectedOptions?.[0];
      if (!select || !option) {
        return;
      }
      await runMutation(async () => {
        await state.api.assignTicket(state.currentTicketId, {
          telegram_user_id: Number(select.value),
          display_name: option.dataset.displayName,
          username: option.dataset.username || null,
        });
        invalidateTicketData(state.currentTicketId);
      });
      await renderRoute();
      showNotice("Назначение обновлено.", "success");
    }
  });
}

async function runMutation(work) {
  document.body.classList.add("is-busy");
  try {
    await work();
  } catch (error) {
    if (error instanceof MiniAppRequestError && error.status === 401) {
      clearStaleLaunchState(error);
      content.innerHTML = renderInitDataMissing(buildLaunchFailureCopy(state.launch, error));
      return;
    }

    const message = resolveErrorMessage(error);
    showNotice(message, "danger");
    if (telegram?.HapticFeedback) {
      telegram.HapticFeedback.notificationOccurred("error");
    }
  } finally {
    document.body.classList.remove("is-busy");
  }
}

async function handleCopy(value, successMessage = "Код приглашения скопирован.") {
  try {
    await navigator.clipboard.writeText(value);
    showNotice(successMessage, "success");
    if (telegram?.HapticFeedback) {
      telegram.HapticFeedback.notificationOccurred("success");
    }
  } catch (_error) {
    showNotice("Не удалось скопировать код.", "danger");
  }
}

function showNotice(message, tone = "neutral") {
  if (!appNotice) {
    return;
  }

  window.clearTimeout(noticeTimeoutId);
  appNotice.hidden = false;
  appNotice.textContent = message;
  appNotice.dataset.tone = tone;
  noticeTimeoutId = window.setTimeout(() => {
    appNotice.hidden = true;
    appNotice.textContent = "";
    delete appNotice.dataset.tone;
  }, 2600);
}

function invalidateTicketCollections() {
  state.cache.dashboard = null;
  state.cache.queue = null;
  state.cache.mine = null;
  state.cache.archive = null;
  state.cache.analytics = {};
  state.cache.admin = null;
}

function invalidateTicketData(ticketId) {
  invalidateTicketCollections();
  if (ticketId) {
    delete state.cache.tickets[ticketId];
    delete state.aiReplyDrafts[ticketId];
  }
}

async function loadDashboard() {
  if (state.cache.dashboard) {
    return state.cache.dashboard;
  }
  state.cache.dashboard = await state.api.getDashboard();
  return state.cache.dashboard;
}

async function loadQueue() {
  if (state.cache.queue) {
    return state.cache.queue;
  }
  state.cache.queue = await state.api.getQueue();
  return state.cache.queue;
}

async function loadMyTickets() {
  if (state.cache.mine) {
    return state.cache.mine;
  }
  state.cache.mine = await state.api.getMyTickets();
  return state.cache.mine;
}

async function loadArchive() {
  if (state.cache.archive) {
    return state.cache.archive;
  }
  state.cache.archive = await state.api.getArchive();
  return state.cache.archive;
}

async function loadAnalytics(windowKey) {
  if (state.cache.analytics[windowKey]) {
    return state.cache.analytics[windowKey];
  }
  state.cache.analytics[windowKey] = await state.api.getAnalytics(windowKey);
  return state.cache.analytics[windowKey];
}

async function loadAdmin() {
  if (state.cache.admin) {
    return state.cache.admin;
  }
  state.cache.admin = await state.api.getOperators();
  return state.cache.admin;
}

async function loadTicket(ticketId) {
  if (state.cache.tickets[ticketId]) {
    return state.cache.tickets[ticketId];
  }
  state.cache.tickets[ticketId] = await state.api.getTicket(ticketId);
  return state.cache.tickets[ticketId];
}

function resolveErrorMessage(error) {
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return "Сервис временно недоступен.";
}

async function resolveLaunchContext() {
  let launchContext = await createTelegramLaunchContext();
  if (launchContext.initData) {
    return launchContext;
  }

  if (launchContext.isTelegramWebApp) {
    launchContext = await createTelegramLaunchContext({ extraWait: true });
  }
  return launchContext;
}

async function getSessionWithRetry() {
  try {
    return await state.api.getSession();
  } catch (error) {
    if (!shouldRetrySessionBootstrap(error)) {
      throw error;
    }

    clearStaleLaunchState(error);
    state.launch = await createTelegramLaunchContext({ extraWait: true });
    state.api = createMiniAppApi(state.launch);
    return state.api.getSession();
  }
}

function shouldRetrySessionBootstrap(error) {
  return (
    error instanceof MiniAppRequestError &&
    error.status === 401 &&
    state.launch?.isTelegramWebApp === true &&
    ["missing_init_data", "invalid_signature", "expired_init_data"].includes(error.code)
  );
}

function clearStaleLaunchState(error) {
  if (
    error instanceof MiniAppRequestError &&
    ["invalid_signature", "expired_init_data", "malformed_init_data"].includes(error.code)
  ) {
    clearPersistedLaunchContext();
  }
}

boot();
