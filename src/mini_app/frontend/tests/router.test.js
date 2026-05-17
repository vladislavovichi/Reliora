import { describe, it, expect } from "vitest";
import { normalizeHashRoute } from "../assets/app/router.js";

describe("normalizeHashRoute", () => {
  it("strips leading hash", () => {
    expect(normalizeHashRoute("#dashboard")).toBe("dashboard");
  });
  it("strips query string", () => {
    expect(normalizeHashRoute("#ticket/42?foo=bar")).toBe("ticket/42");
  });
  it("strips leading slashes", () => {
    expect(normalizeHashRoute("#/dashboard")).toBe("dashboard");
  });
  it("handles empty string", () => {
    expect(normalizeHashRoute("")).toBe("");
  });
  it("handles null", () => {
    expect(normalizeHashRoute(null)).toBe("");
  });
  it("handles undefined", () => {
    expect(normalizeHashRoute(undefined)).toBe("");
  });
  it("handles ticket sub-route", () => {
    expect(normalizeHashRoute("#ticket/123")).toBe("ticket/123");
  });
  it("trims whitespace", () => {
    expect(normalizeHashRoute("#queue ")).toBe("queue");
  });
});
