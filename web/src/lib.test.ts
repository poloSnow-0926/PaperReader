import { describe, expect, it } from "vitest";
import {
  DEFAULT_FILTERS, filterPapers, filtersFromQuery, filtersToQuery,
  sanitizeUserData, toBibtex, updateEntry,
} from "./lib";
import type { Paper } from "./types";

const base: Paper = {
  id: "2503.14476", title: "DAPO: An Open-Source LLM Reinforcement Learning System at Scale",
  authors: ["Qiying Yu", "Zheng Zhang"], n_authors: 30, published: "2025-03-18",
  abstract: "We propose DAPO.", category: "reasoning_rl", secondary_category: "infra",
  tldr: "改进 GRPO", source: { type: "published", venue: "NeurIPS 2025", honor: "oral" },
  citations: 500, influential_citations: 80, citations_per_month: 25,
  url: "https://arxiv.org/abs/2503.14476", vetting: "published",
};
const weak: Paper = { ...base, id: "2601.00001", title: "Some paper", category: "agent_rl",
  secondary_category: null, vetting: "unvetted", citations: 0, citations_per_month: 0,
  source: { type: "preprint", venue: null, honor: null }, published: "2026-01-02" };

describe("filterPapers", () => {
  it("hides unvetted by default and matches secondary category", () => {
    const r = filterPapers([base, weak], { ...DEFAULT_FILTERS, cat: "infra" }, {});
    expect(r.map((p) => p.id)).toEqual(["2503.14476"]);
    expect(filterPapers([base, weak], { ...DEFAULT_FILTERS, vetted: false }, {})).toHaveLength(2);
  });

  it("filters by personal status and search terms", () => {
    const user = updateEntry({}, weak.id, { status: "read" });
    const f = { ...DEFAULT_FILTERS, vetted: false, status: "read" };
    expect(filterPapers([base, weak], f, user).map((p) => p.id)).toEqual([weak.id]);
    expect(filterPapers([base, weak], { ...DEFAULT_FILTERS, q: "dapo grpo" }, {})).toHaveLength(1);
  });
});

describe("url state", () => {
  it("round-trips filters and omits defaults", () => {
    expect(filtersToQuery(DEFAULT_FILTERS)).toBe("");
    const f = { ...DEFAULT_FILTERS, cat: "reasoning_rl", vetted: false, sort: "date" as const };
    expect(filtersFromQuery(filtersToQuery(f))).toEqual(f);
  });
});

describe("user data", () => {
  it("removes entries that become empty", () => {
    const d = updateEntry(updateEntry({}, "x", { rating: 5 }), "x", { rating: 0 });
    expect(d).toEqual({});
  });
  it("sanitizes imported data", () => {
    const d = sanitizeUserData({ a: { status: "bogus", rating: 9, note: "hi" }, b: 3 });
    expect(d.a).toMatchObject({ status: "none", rating: 0, note: "hi" });
    expect(d.b).toBeUndefined();
    expect(() => sanitizeUserData([])).toThrow();
  });
});

it("builds bibtex with others for truncated authors", () => {
  const b = toBibtex(base);
  expect(b).toContain("@article{yu2025dapo,");
  expect(b).toContain("Qiying Yu and Zheng Zhang and others");
  expect(b).toContain("journal = {NeurIPS 2025}");
});
