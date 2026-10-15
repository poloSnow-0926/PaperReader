import { useEffect, useMemo, useRef, useState } from "react";
import {
  DEFAULT_FILTERS, EMPTY_ENTRY, STORAGE_KEY, filterPapers, filtersFromQuery, filtersToQuery,
  loadUserData, sanitizeUserData, toBibtex, updateEntry, type Filters, type SortKey,
} from "./lib";
import type { Dataset, Paper, ReadStatus, UserData, UserEntry } from "./types";

const PAGE_SIZE = 50;

const STATUS_LABEL: Record<ReadStatus, string> = {
  none: "未标记", to_read: "想读", reading: "在读", read: "已读",
};
const SOURCE_LABEL = { published: "已录用", preprint: "预印本", tech_report: "技术报告" };
const VETTING_LABEL: Record<string, string> = {
  seed: "必读", cited: "引用活跃", new: "新论文", unvetted: "待观察",
};

export default function App() {
  const [data, setData] = useState<Dataset | null>(null);
  const [error, setError] = useState("");
  const [filters, setFilters] = useState<Filters>(() => filtersFromQuery(location.search));
  const [user, setUser] = useState<UserData>(() => loadUserData());
  const [limit, setLimit] = useState(PAGE_SIZE);

  useEffect(() => {
    fetch(`${import.meta.env.BASE_URL}papers.json`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(setData)
      .catch((e) => setError(`数据加载失败：${e.message}。请先运行 python -m paper_radar.build`));
  }, []);

  // 筛选条件写入 URL，方便分享
  useEffect(() => {
    history.replaceState(null, "", `${location.pathname}${filtersToQuery(filters)}`);
    setLimit(PAGE_SIZE);
  }, [filters]);

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(user));
  }, [user]);

  const years = useMemo(
    () => [...new Set((data?.papers ?? []).map((p) => p.published.slice(0, 4)))].sort().reverse(),
    [data],
  );
  const results = useMemo(
    () => (data ? filterPapers(data.papers, filters, user) : []),
    [data, filters, user],
  );

  const set = <K extends keyof Filters>(k: K, v: Filters[K]) => setFilters((f) => ({ ...f, [k]: v }));
  const patch = (id: string, p: Partial<UserEntry>) => setUser((u) => updateEntry(u, id, p));

  if (error) return <main className="container"><p role="alert">{error}</p></main>;
  if (!data) return <main className="container"><p>加载中…</p></main>;

  const counts = Object.values(user).reduce(
    (acc, e) => ({ ...acc, [e.status]: (acc[e.status] ?? 0) + 1 }),
    {} as Record<string, number>,
  );

  return (
    <main className="container">
      <header className="header">
        <div>
          <h1>Paper Radar</h1>
          <p className="muted">
            LLM 后训练 / 强化学习论文 · 共 {data.papers.length} 篇 · 数据更新于 {data.generated_at}
          </p>
        </div>
        <UserDataTools user={user} setUser={setUser} counts={counts} />
      </header>

      <nav className="tabs" aria-label="细分方向">
        <button aria-pressed={!filters.cat} onClick={() => set("cat", "")}>全部</button>
        {Object.entries(data.categories).map(([k, desc]) => (
          <button key={k} aria-pressed={filters.cat === k} title={desc} onClick={() => set("cat", k)}>
            {desc.split("：")[0]}
          </button>
        ))}
      </nav>

      <section className="filters" aria-label="筛选">
        <input
          type="search" placeholder="搜索标题、摘要、作者、我的笔记…" aria-label="搜索"
          value={filters.q} onChange={(e) => set("q", e.target.value)}
        />
        <label>年份
          <select value={filters.year} onChange={(e) => set("year", e.target.value)}>
            <option value="">全部</option>
            {years.map((y) => <option key={y}>{y}</option>)}
          </select>
        </label>
        <label>来源
          <select value={filters.source} onChange={(e) => set("source", e.target.value)}>
            <option value="">全部</option>
            {Object.entries(SOURCE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </label>
        <label>我的
          <select value={filters.status} onChange={(e) => set("status", e.target.value)}>
            <option value="">全部</option>
            {Object.entries(STATUS_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            <option value="liked">我评 4 分以上</option>
          </select>
        </label>
        <label>排序
          <select value={filters.sort} onChange={(e) => set("sort", e.target.value as SortKey)}>
            <option value="momentum">影响力（月均引用）</option>
            <option value="citations">总引用</option>
            <option value="date">最新</option>
            <option value="my_rating">我的评分</option>
          </select>
        </label>
        <label className="check">
          <input type="checkbox" checked={filters.vetted} onChange={(e) => set("vetted", e.target.checked)} />
          只看靠谱的
        </label>
        {filtersToQuery(filters) && (
          <button className="link" onClick={() => setFilters(DEFAULT_FILTERS)}>重置</button>
        )}
      </section>

      <p className="muted" aria-live="polite">{results.length} 篇结果</p>
      <ul className="list">
        {results.slice(0, limit).map((p) => (
          <PaperCard key={p.id} paper={p} entry={user[p.id] ?? EMPTY_ENTRY}
            categories={data.categories} onPatch={(x) => patch(p.id, x)} />
        ))}
      </ul>
      {results.length > limit && (
        <button className="more" onClick={() => setLimit((l) => l + PAGE_SIZE)}>
          加载更多（还有 {results.length - limit} 篇）
        </button>
      )}
    </main>
  );
}

function PaperCard({ paper: p, entry, categories, onPatch }: {
  paper: Paper; entry: UserEntry; categories: Record<string, string>;
  onPatch: (p: Partial<UserEntry>) => void;
}) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const copyBib = async () => {
    await navigator.clipboard.writeText(toBibtex(p));
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };
  const authors = p.authors.slice(0, 3).join(", ") + (p.n_authors > 3 ? " 等" : "");

  return (
    <li className={`card status-${entry.status}`}>
      <div className="badges">
        <span className={`badge src-${p.source.type}`}>
          {p.source.venue ?? SOURCE_LABEL[p.source.type]}
          {p.source.honor && ` · ${p.source.honor === "oral" ? "Oral" : "Spotlight"}`}
        </span>
        {VETTING_LABEL[p.vetting] && <span className={`badge v-${p.vetting}`}>{VETTING_LABEL[p.vetting]}</span>}
        <span className="badge cat">{categories[p.category]?.split("：")[0] ?? p.category}</span>
        <span className="muted small">{p.published}</span>
      </div>
      <h2 className="title"><a href={p.url} target="_blank" rel="noopener noreferrer">{p.title}</a></h2>
      <p className="muted small">{authors}</p>
      {p.tldr && <p className="tldr"><span className="small muted">AI 总结 · </span>{p.tldr}</p>}
      <p className="small muted">
        引用 {p.citations ?? "—"}
        {p.influential_citations != null && ` · 高影响力 ${p.influential_citations}`}
        {p.citations_per_month != null && ` · 月均 ${p.citations_per_month}`}
      </p>

      <div className="actions">
        <div role="group" aria-label="阅读状态" className="seg">
          {(["to_read", "reading", "read"] as ReadStatus[]).map((s) => (
            <button key={s} aria-pressed={entry.status === s}
              onClick={() => onPatch({ status: entry.status === s ? "none" : s })}>
              {STATUS_LABEL[s]}
            </button>
          ))}
        </div>
        <div role="group" aria-label="我的评分" className="stars">
          {[1, 2, 3, 4, 5].map((n) => (
            <button key={n} aria-label={`${n} 分`} aria-pressed={entry.rating >= n}
              onClick={() => onPatch({ rating: entry.rating === n ? 0 : n })}>★</button>
          ))}
        </div>
        <button className="link" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
          {open ? "收起" : entry.note ? "笔记 ✎" : "摘要 / 笔记"}
        </button>
        <button className="link" onClick={copyBib}>{copied ? "已复制" : "BibTeX"}</button>
      </div>

      {open && (
        <div className="detail">
          <p className="small">{p.abstract}</p>
          <label className="small">我的笔记
            <textarea rows={3} defaultValue={entry.note} placeholder="读后感、可借鉴的点…"
              onBlur={(e) => e.target.value !== entry.note && onPatch({ note: e.target.value })} />
          </label>
        </div>
      )}
    </li>
  );
}

function UserDataTools({ user, setUser, counts }: {
  user: UserData; setUser: (u: UserData) => void; counts: Record<string, number>;
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  const exportData = () => {
    const blob = new Blob([JSON.stringify(user, null, 1)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `paper-radar-我的数据-${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
  };
  const importData = async (file: File) => {
    try {
      const incoming = sanitizeUserData(JSON.parse(await file.text()));
      // 合并：同一篇论文以较新的修改为准
      const merged = { ...user };
      for (const [id, e] of Object.entries(incoming)) {
        if (!merged[id] || e.updated > merged[id].updated) merged[id] = e;
      }
      setUser(merged);
      alert(`已导入 ${Object.keys(incoming).length} 条记录`);
    } catch (e) {
      alert(`导入失败：${(e as Error).message}`);
    }
  };
  return (
    <div className="tools small">
      <span className="muted">
        想读 {counts.to_read ?? 0} · 在读 {counts.reading ?? 0} · 已读 {counts.read ?? 0}
      </span>
      <button className="link" onClick={exportData}>导出我的数据</button>
      <button className="link" onClick={() => fileRef.current?.click()}>导入</button>
      <input ref={fileRef} type="file" accept="application/json" hidden
        onChange={(e) => { const f = e.target.files?.[0]; if (f) importData(f); e.target.value = ""; }} />
    </div>
  );
}
