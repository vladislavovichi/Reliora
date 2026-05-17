import { DEFAULT_ROUTE, NAV_ROUTES } from "./state.js";

export function syncRoute({ state, hash, navStrip, buildNavigation }) {
  const normalizedHash = normalizeHashRoute(hash);
  if (normalizedHash.startsWith("ticket/") && normalizedHash.split("/")[1]) {
    state.currentRoute = "ticket";
    state.currentTicketId = normalizedHash.split("/")[1] ?? null;
    navStrip.innerHTML = buildNavigation(state.session.access.role, "");
    return;
  }

  const route = NAV_ROUTES.has(normalizedHash) ? normalizedHash : DEFAULT_ROUTE;
  state.currentRoute =
    route === "admin" && state.session.access.role !== "super_admin" ? DEFAULT_ROUTE : route;
  state.currentTicketId = null;
  navStrip.innerHTML = buildNavigation(state.session.access.role, state.currentRoute);
}

export function normalizeHashRoute(hash) {
  return String(hash || "")
    .replace(/^#/, "")
    .split("?")[0]
    .replace(/^\/+/, "")
    .trim();
}
