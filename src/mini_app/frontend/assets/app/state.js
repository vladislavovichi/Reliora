export const DEFAULT_ROUTE = "dashboard";
export const NAV_ROUTES = new Set(["dashboard", "queue", "mine", "archive", "analytics", "admin"]);

export function createInitialState() {
  return {
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
    aiSettingsDraft: null,
  };
}

export function invalidateTicketCollections(state) {
  state.cache.dashboard = null;
  state.cache.queue = null;
  state.cache.mine = null;
  state.cache.archive = null;
  state.cache.analytics = {};
  state.cache.admin = null;
}

export function invalidateTicketData(state, ticketId) {
  invalidateTicketCollections(state);
  if (ticketId) {
    delete state.cache.tickets[ticketId];
    delete state.aiReplyDrafts[ticketId];
  }
}

export async function loadDashboard(state) {
  if (state.cache.dashboard) {
    return state.cache.dashboard;
  }
  state.cache.dashboard = await state.api.getOperatorDashboard();
  return state.cache.dashboard;
}

export async function loadQueue(state) {
  if (state.cache.queue) {
    return state.cache.queue;
  }
  state.cache.queue = await state.api.getQueue();
  return state.cache.queue;
}

export async function loadMyTickets(state) {
  if (state.cache.mine) {
    return state.cache.mine;
  }
  state.cache.mine = await state.api.getMyTickets();
  return state.cache.mine;
}

export async function loadArchive(state) {
  if (state.cache.archive) {
    return state.cache.archive;
  }
  state.cache.archive = await state.api.getArchive();
  return state.cache.archive;
}

export async function loadAnalytics(state, windowKey) {
  if (state.cache.analytics[windowKey]) {
    return state.cache.analytics[windowKey];
  }
  state.cache.analytics[windowKey] = await state.api.getAnalytics(windowKey);
  return state.cache.analytics[windowKey];
}

export async function loadAdmin(state) {
  if (state.cache.admin) {
    return state.cache.admin;
  }
  const [operators, aiSettings] = await Promise.all([
    state.api.getOperators(),
    state.api.getAISettings(),
  ]);
  state.cache.admin = { operators, aiSettings };
  return state.cache.admin;
}

export async function loadTicket(state, ticketId) {
  if (state.cache.tickets[ticketId]) {
    return state.cache.tickets[ticketId];
  }
  state.cache.tickets[ticketId] = await state.api.getTicket(ticketId);
  return state.cache.tickets[ticketId];
}
