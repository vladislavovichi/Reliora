import { describe, it, expect } from "vitest";
import {
  escapeHtml,
  escapeAttribute,
  formatDuration,
  renderBar,
  applyTicketFilters,
  applyArchiveFilters,
  buildArchiveCategories,
  findArchiveCategory,
  statusLabel,
  priorityLabel,
} from "../assets/render-utils.js";

describe("escapeHtml", () => {
  it("escapes angle brackets", () => {
    expect(escapeHtml("<script>")).toBe("&lt;script&gt;");
  });
  it("escapes ampersand", () => {
    expect(escapeHtml("a & b")).toBe("a &amp; b");
  });
  it("escapes double quotes", () => {
    expect(escapeHtml('"hello"')).toBe("&quot;hello&quot;");
  });
  it("escapes single quotes", () => {
    expect(escapeHtml("it's")).toBe("it&#39;s");
  });
  it("coerces non-strings", () => {
    expect(escapeHtml(42)).toBe("42");
  });
  it("leaves safe strings untouched", () => {
    expect(escapeHtml("hello world")).toBe("hello world");
  });
});

describe("escapeAttribute", () => {
  it("returns empty string for null", () => {
    expect(escapeAttribute(null)).toBe("");
  });
  it("escapes like escapeHtml", () => {
    expect(escapeAttribute("<b>")).toBe("&lt;b&gt;");
  });
});

describe("formatDuration", () => {
  it("returns em-dash for null", () => {
    expect(formatDuration(null)).toBe("—");
  });
  it("returns em-dash for undefined", () => {
    expect(formatDuration(undefined)).toBe("—");
  });
  it("handles zero (boundary: zero is not falsy-treated as missing)", () => {
    expect(formatDuration(0)).toBe("0 сек");
  });
  it("formats seconds", () => {
    expect(formatDuration(45)).toBe("45 сек");
  });
  it("formats minutes at boundary (60s)", () => {
    expect(formatDuration(60)).toBe("1 мин");
  });
  it("rounds minutes", () => {
    expect(formatDuration(90)).toBe("2 мин");
  });
  it("formats hours at boundary (3600s)", () => {
    expect(formatDuration(3600)).toBe("1 ч");
  });
  it("formats hours", () => {
    expect(formatDuration(7200)).toBe("2 ч");
  });
});

describe("renderBar", () => {
  it("clamps minimum width to 4%", () => {
    expect(renderBar("x", 0, 100, "0")).toContain("width:4%");
  });
  it("caps maximum width at 100%", () => {
    expect(renderBar("x", 200, 100, "200")).toContain("width:100%");
  });
  it("handles zero maxValue without division by zero", () => {
    const html = renderBar("x", 0, 0, "0");
    expect(html).toContain("width:4%");
  });
  it("uses valueLabel when provided", () => {
    expect(renderBar("label", 5, 10, "five")).toContain("five");
  });
});

describe("applyTicketFilters", () => {
  const items = [
    { public_number: "#1", subject: "Login issue", mini_title: "Auth" },
    { public_number: "#2", subject: "Payment problem", mini_title: "Billing" },
  ];

  it("returns all items for empty search", () => {
    expect(applyTicketFilters(items, { search: "" })).toHaveLength(2);
  });
  it("filters by subject", () => {
    const result = applyTicketFilters(items, { search: "Login" });
    expect(result).toHaveLength(1);
    expect(result[0].public_number).toBe("#1");
  });
  it("is case-insensitive", () => {
    expect(applyTicketFilters(items, { search: "login" })).toHaveLength(1);
  });
  it("filters by mini_title", () => {
    expect(applyTicketFilters(items, { search: "Billing" })).toHaveLength(1);
  });
  it("returns empty for no match", () => {
    expect(applyTicketFilters(items, { search: "zzz" })).toHaveLength(0);
  });
});

describe("applyArchiveFilters", () => {
  const items = [
    {
      public_number: "#3",
      subject: "Bug",
      mini_title: null,
      category_title: "Technical",
      category_code: "tech",
    },
    {
      public_number: "#4",
      subject: "Refund",
      mini_title: null,
      category_title: "Billing",
      category_code: "bill",
    },
  ];

  it("returns all when search and category are empty", () => {
    expect(applyArchiveFilters(items, { search: "", category: "" })).toHaveLength(2);
  });
  it("filters by category_title", () => {
    const result = applyArchiveFilters(items, { search: "", category: "Technical" });
    expect(result).toHaveLength(1);
    expect(result[0].public_number).toBe("#3");
  });
  it("combines search and category filters", () => {
    const result = applyArchiveFilters(items, { search: "Bug", category: "tech" });
    expect(result).toHaveLength(1);
  });
});

describe("buildArchiveCategories", () => {
  it("deduplicates and counts", () => {
    const items = [
      { category_title: "Tech", category_code: "tech" },
      { category_title: "Tech", category_code: "tech" },
      { category_title: "Billing", category_code: "billing" },
    ];
    const cats = buildArchiveCategories(items);
    expect(cats).toHaveLength(2);
    expect(cats[0].title).toBe("Tech");
    expect(cats[0].count).toBe(2);
  });
  it("skips items with no category info", () => {
    expect(buildArchiveCategories([{ category_title: "", category_code: "" }])).toHaveLength(0);
  });
  it("sorts by count descending, then title ascending", () => {
    const items = [
      { category_title: "B", category_code: "b" },
      { category_title: "A", category_code: "a" },
      { category_title: "A", category_code: "a" },
    ];
    const cats = buildArchiveCategories(items);
    expect(cats[0].title).toBe("A");
    expect(cats[1].title).toBe("B");
  });
});

describe("findArchiveCategory", () => {
  const categories = [
    { value: "tech", title: "Technical", code: "tech", count: 3 },
    { value: "billing", title: "Billing", code: "bill", count: 1 },
  ];

  it("finds by value", () => {
    expect(findArchiveCategory(categories, "tech")?.title).toBe("Technical");
  });
  it("finds by title", () => {
    expect(findArchiveCategory(categories, "Technical")?.code).toBe("tech");
  });
  it("returns null for empty string", () => {
    expect(findArchiveCategory(categories, "")).toBeNull();
  });
  it("returns null for no match", () => {
    expect(findArchiveCategory(categories, "unknown")).toBeNull();
  });
});

describe("statusLabel / priorityLabel", () => {
  it("maps known status", () => {
    expect(statusLabel("new")).toBe("Новая");
    expect(statusLabel("closed")).toBe("Закрыта");
  });
  it("falls back to raw value for unknown status", () => {
    expect(statusLabel("mystery")).toBe("mystery");
  });
  it("maps known priority", () => {
    expect(priorityLabel("urgent")).toBe("Срочный");
  });
  it("falls back to raw value for unknown priority", () => {
    expect(priorityLabel("unknown")).toBe("unknown");
  });
});
