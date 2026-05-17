import { describe, it, expect } from "vitest";
import {
  createInitialState,
  invalidateTicketCollections,
  invalidateTicketData,
  DEFAULT_ROUTE,
  NAV_ROUTES,
} from "../assets/app/state.js";

describe("constants", () => {
  it("DEFAULT_ROUTE is dashboard", () => {
    expect(DEFAULT_ROUTE).toBe("dashboard");
  });
  it("NAV_ROUTES contains expected routes", () => {
    expect(NAV_ROUTES.has("dashboard")).toBe(true);
    expect(NAV_ROUTES.has("queue")).toBe(true);
    expect(NAV_ROUTES.has("admin")).toBe(true);
  });
});

describe("createInitialState", () => {
  it("sets currentRoute to DEFAULT_ROUTE", () => {
    expect(createInitialState().currentRoute).toBe(DEFAULT_ROUTE);
  });
  it("initializes all collection caches to null", () => {
    const { cache } = createInitialState();
    expect(cache.dashboard).toBeNull();
    expect(cache.queue).toBeNull();
    expect(cache.mine).toBeNull();
    expect(cache.archive).toBeNull();
    expect(cache.admin).toBeNull();
  });
  it("initializes analytics and tickets to empty objects", () => {
    const { cache } = createInitialState();
    expect(cache.analytics).toEqual({});
    expect(cache.tickets).toEqual({});
  });
  it("initializes api and session to null", () => {
    const state = createInitialState();
    expect(state.api).toBeNull();
    expect(state.session).toBeNull();
  });
});

describe("invalidateTicketCollections", () => {
  it("clears all collection caches", () => {
    const state = createInitialState();
    state.cache.dashboard = { data: "x" };
    state.cache.queue = [1, 2, 3];
    state.cache.mine = [4];
    state.cache.archive = [5];
    state.cache.admin = { operators: [] };
    invalidateTicketCollections(state);
    expect(state.cache.dashboard).toBeNull();
    expect(state.cache.queue).toBeNull();
    expect(state.cache.mine).toBeNull();
    expect(state.cache.archive).toBeNull();
    expect(state.cache.admin).toBeNull();
    expect(state.cache.analytics).toEqual({});
  });
  it("does not touch ticket or aiReplyDrafts caches", () => {
    const state = createInitialState();
    state.cache.tickets[99] = { id: 99 };
    state.aiReplyDrafts[99] = "draft";
    invalidateTicketCollections(state);
    expect(state.cache.tickets[99]).toBeDefined();
    expect(state.aiReplyDrafts[99]).toBe("draft");
  });
});

describe("invalidateTicketData", () => {
  it("removes specific ticket from cache and drafts", () => {
    const state = createInitialState();
    state.cache.tickets[42] = { id: 42 };
    state.aiReplyDrafts[42] = "reply draft";
    invalidateTicketData(state, 42);
    expect(state.cache.tickets[42]).toBeUndefined();
    expect(state.aiReplyDrafts[42]).toBeUndefined();
  });
  it("also invalidates collection caches", () => {
    const state = createInitialState();
    state.cache.dashboard = { data: "x" };
    invalidateTicketData(state, 1);
    expect(state.cache.dashboard).toBeNull();
  });
  it("skips ticket cache removal when ticketId is null", () => {
    const state = createInitialState();
    state.cache.tickets[1] = { id: 1 };
    invalidateTicketData(state, null);
    expect(state.cache.tickets[1]).toBeDefined();
  });
});
