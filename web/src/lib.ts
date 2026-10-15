import type { Paper, ReadStatus, UserData, UserEntry, Vetting } from "./types";

// ---------- 个人数据（localStorage） ----------
export const STORAGE_KEY = "paper-radar:user:v1";

export const EMPTY_ENTRY: UserEntry = { status: "none", rating: 0, note: "", updated: "" };

export function loadUserData(storage: Pick<Storage, "getItem"> = localStorage): UserData {
  try {
    const raw = storage.getItem(STORAGE_KEY);
    return raw ? sanitizeUserData(JSON.parse(raw)) : {};
  } catch {
    return {};
  }
}

const STATUSES: ReadStatus[] = ["none", "to_read", "reading", "read"];

/** 导入或读取时校验结构，丢弃不合法的条目 */
export function sanitizeUserData(raw: unknown): UserData {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) throw new Error("格式不正确");
  const out: UserData = {};
  for (const [id, v] of Object.entries(raw as Record<string, unknown>)) {
    if (!v || typeof v !== "object") continue;
    const e = v as Partial<UserEntry>;
    const entry: UserEntry = {
      status: STATUSES.includes(e.status as ReadStatus) ? (e.status as ReadStatus) : "none",
      rating: Number.isInteger(e.rating) && e.rating! >= 0 && e.rating! <= 5 ? e.rating! : 0,
      note: typeof e.note === "string" ? e.note.slice(0, 5000) : "",
      updated: typeof e.updated === "string" ? e.updated : "",
    };
    if (!isEmpty(entry)) out[id] = entry;
  }
  return out;
}

export function isEmpty(e: UserEntry): boolean {
  return e.status === "none" && e.rating === 0 && !e.note.trim();
}

export function updateEntry(data: UserData, id: string, patch: Partial<UserEntry>): UserData {
  const next = { ...(data[id] ?? EMPTY_ENTRY), ...patch, updated: new Date().toISOString() };
  const copy = { ...data };
  if (isEmpty(next)) delete copy[id];
  else copy[id] = next;
  return copy;
}

// ---------- 筛选与排序 ----------
export type SortKey = "date" | "citations" | "momentum" | "my_rating";

export interface Filters {
  q: string;
  cat: string; // "" 表示全部
  year: string;
  source: string;
  vetted: boolean; // 只看"靠谱"的（排除 unvetted）
  status: string; // "" / none / to_read / reading / read / liked
  sort: SortKey;
}

export const DEFAULT_FILTERS: Filters = {
  q: "", cat: "", year: "", source: "", vetted: true, status: "", sort: "momentum",
};

const VETTED: Vetting[] = ["seed", "published", "tech_report", "cited", "new"];

export function filterPapers(papers: Paper[], f: Filters, user: UserData): Paper[] {
  const q = f.q.trim().toLowerCase();
  const res = papers.filter((p) => {
    if (f.cat && p.category !== f.cat && p.secondary_category !== f.cat) return false;
    if (f.year && !p.published.startsWith(f.year)) return false;
    if (f.source && p.source.type !== f.source) return false;
    if (f.vetted && !VETTED.includes(p.vetting)) return false;
    const u = user[p.id] ?? EMPTY_ENTRY;
    if (f.status === "liked" ? u.rating < 4 : f.status && u.status !== f.status) return false;
    if (q) {
      const hay = `${p.title} ${p.tldr} ${p.abstract} ${p.authors.join(" ")} ${u.note}`.toLowerCase();
      if (!q.split(/\s+/).every((t) => hay.includes(t))) return false;
    }
    return true;
  });
  const key: Record<SortKey, (p: Paper) => number> = {
    date: (p) => Date.parse(p.published),
    citations: (p) => p.citations ?? -1,
    momentum: (p) => (p.vetting === "seed" ? 1e6 : 0) + (p.citations_per_month ?? -1),
    my_rating: (p) => (user[p.id]?.rating ?? 0) * 1e13 + Date.parse(p.published),
  };
  const k = key[f.sort];
  return res.sort((a, b) => k(b) - k(a));
}

// ---------- URL 同步（可分享的筛选链接） ----------
export function filtersToQuery(f: Filters): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(f)) {
    const d = DEFAULT_FILTERS[k as keyof Filters];
    if (v !== d) p.set(k, String(v));
  }
  const s = p.toString();
  return s ? `?${s}` : "";
}

export function filtersFromQuery(search: string): Filters {
  const p = new URLSearchParams(search);
  const sort = p.get("sort") as SortKey | null;
  return {
    q: p.get("q") ?? "",
    cat: p.get("cat") ?? "",
    year: p.get("year") ?? "",
    source: p.get("source") ?? "",
    vetted: p.get("vetted") !== "false",
    status: p.get("status") ?? "",
    sort: sort && ["date", "citations", "momentum", "my_rating"].includes(sort) ? sort : "momentum",
  };
}

// ---------- BibTeX ----------
function bibEscape(s: string): string {
  return s.replace(/[{}\\]/g, "").replace(/([&%$#_])/g, "\\$1");
}

export function toBibtex(p: Paper): string {
  const year = p.published.slice(0, 4);
  const first = (p.authors[0] ?? "anon").split(/\s+/).pop()!.toLowerCase().replace(/[^a-z]/g, "");
  const word = (p.title.match(/[A-Za-z]{4,}/)?.[0] ?? "paper").toLowerCase();
  const authors = p.authors.length < p.n_authors ? [...p.authors, "others"] : p.authors;
  const lines = [
    `@article{${first}${year}${word},`,
    `  title = {${bibEscape(p.title)}},`,
    `  author = {${authors.map(bibEscape).join(" and ")}},`,
    `  journal = {${p.source.type === "published" && p.source.venue ? bibEscape(p.source.venue) : `arXiv preprint arXiv:${p.id}`}},`,
    `  year = {${year}},`,
    `  url = {${p.url}},`,
    `}`,
  ];
  return lines.join("\n");
}
