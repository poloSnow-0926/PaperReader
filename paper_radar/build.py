"""全量流水线：抓取候选 → LLM 分类 + 一句话总结 → 引用与来源标签 → 输出网站数据。

用法：
  uv run python -m paper_radar.build                 # 近两年全量
  uv run python -m paper_radar.build --months 1      # 只跑最近 1 个月（试跑 / 每周更新）
  uv run python -m paper_radar.build --dry-run       # 只抓取并估算成本，不调用 LLM
输出：web/public/papers.json
"""

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime

from . import arxiv, prompts, semantic_scholar
from .config import (CATEGORIES, PRICE_INPUT_CACHE_MISS, PRICE_OUTPUT, ROOT)
from .harvest import harvest_month, months_between
from .llm import LLM
from .venue import source_label

OUT = ROOT / "web" / "public" / "papers.json"

# 奠基 / 必读种子：不受时间范围限制，一定收录
SEEDS = [
    "1707.06347", "2203.02155", "2212.08073", "2305.18290", "2305.20050", "2312.08935",
    "2402.01306", "2402.03300", "2405.11143", "2405.14734", "2409.19256", "2411.15124",
    "2501.12599", "2501.12948", "2503.09516", "2503.14476", "2503.20783",
]

# "靠谱"门槛（只影响默认显示，网站上可以关掉过滤看全部）
NEW_PAPER_DAYS = 60          # 太新的论文还没有引用，单独标为"新"
MIN_CITATIONS_PER_MONTH = 1.0  # 预印本：月均引用达到该值视为靠谱
MIN_CITATIONS_ABS = 5


def _age_months(published: str, today: date) -> float:
    d = datetime.strptime(published, "%Y-%m-%d").date()
    return max((today - d).days / 30.4, 0.5)


def vetting(p: dict, today: date) -> str:
    """返回 seed / published / tech_report / cited / new / unvetted。"""
    if p["arxiv_id"] in SEEDS:
        return "seed"
    if p["source"]["type"] == "published":
        return "published"
    cites = (p.get("s2") or {}).get("citation_count")
    age = _age_months(p["published"], today)
    if cites is not None and cites >= MIN_CITATIONS_ABS and cites / age >= MIN_CITATIONS_PER_MONTH:
        return "cited"
    if p["source"]["type"] == "tech_report":
        return "tech_report"
    if age * 30.4 <= NEW_PAPER_DAYS:
        return "new"
    return "unvetted"


def classify_all(llm: LLM, papers: list[dict], workers: int = 8) -> dict[str, dict]:
    out: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(llm.json_call, "classify", prompts.CLASSIFY_SYSTEM,
                            prompts.classify_user(p), 800): p["arxiv_id"] for p in papers}
        for i, f in enumerate(as_completed(futs), 1):
            aid = futs[f]
            try:
                out[aid] = prompts.validate_classification(f.result())
            except Exception as e:
                print(f"  分类失败 {aid}: {e}")
            if i % 200 == 0 or i == len(futs):
                u = llm.usage
                cost = (u.prompt_tokens * PRICE_INPUT_CACHE_MISS + u.completion_tokens * PRICE_OUTPUT) / 1e6
                print(f"  {i}/{len(futs)}  累计 ${cost:.2f}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", type=int, default=24)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--cached-only", action="store_true",
                    help="只用已缓存的分类结果生成数据，不再调用任何付费或限流接口")
    args = ap.parse_args()

    today = date.today()
    # 往前推 months 个月（含当月）
    idx = today.year * 12 + (today.month - 1) - (args.months - 1)
    start = date(idx // 12, idx % 12 + 1, 1)

    print(f"抓取 {start:%Y-%m} 至 {today:%Y-%m} 的候选论文…")
    candidates: dict[str, dict] = {}
    for y, m in months_between(start, today):
        batch = harvest_month(y, m)
        for p in batch:
            candidates[p["arxiv_id"]] = p
        print(f"  {y}-{m:02d}: {len(batch)} 篇（累计 {len(candidates)}）")
    missing_seeds = [s for s in SEEDS if s not in candidates]
    for p in arxiv.fetch_by_ids(missing_seeds):
        candidates[p["arxiv_id"]] = p
    papers = list(candidates.values())

    est_cost = len(papers) * (750 * PRICE_INPUT_CACHE_MISS + 400 * PRICE_OUTPUT) / 1e6
    print(f"候选共 {len(papers)} 篇，分类成本估算约 ${est_cost:.2f}（未计本地缓存命中）")
    if args.dry_run:
        return

    llm = LLM()
    if args.cached_only:
        # 只用已有缓存，不再调用 LLM 和 Semantic Scholar
        papers = [p for p in papers if llm.has_cache("classify", prompts.CLASSIFY_SYSTEM,
                                                     prompts.classify_user(p))]
        print(f"仅使用缓存：已分类 {len(papers)} 篇")
    print("LLM 分类…")
    cls = classify_all(llm, papers)
    relevant = [p for p in papers if cls.get(p["arxiv_id"], {}).get("relevant")
                or p["arxiv_id"] in SEEDS]
    print(f"相关论文 {len(relevant)} 篇")

    if args.cached_only:
        s2 = {}
    else:
        print("获取 Semantic Scholar 引用数据…")
        s2 = semantic_scholar.fetch_batch([p["arxiv_id"] for p in relevant])
        print(f"  命中 {len(s2)}/{len(relevant)}")

    records = []
    for p in relevant:
        c = cls.get(p["arxiv_id"]) or {}
        s = s2.get(p["arxiv_id"])
        rec = {
            "id": p["arxiv_id"],
            "title": p["title"],
            "authors": p["authors"][:8],
            "n_authors": len(p["authors"]),
            "published": p["published"],
            "abstract": p["abstract"],
            "category": c.get("primary_category") or "analysis",
            "secondary_category": c.get("secondary_category"),
            "tldr": c.get("tldr_zh", ""),
            "source": source_label(p, s),
            "citations": (s or {}).get("citation_count"),
            "influential_citations": (s or {}).get("influential_citation_count"),
            "url": f"https://arxiv.org/abs/{p['arxiv_id']}",
            "s2": s,
        }
        cites = rec["citations"]
        rec["citations_per_month"] = round(cites / _age_months(p["published"], today), 2) if cites is not None else None
        rec["vetting"] = vetting(rec | {"arxiv_id": p["arxiv_id"]}, today)
        del rec["s2"]
        records.append(rec)

    records.sort(key=lambda r: r["published"], reverse=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "generated_at": today.isoformat(),
        "categories": CATEGORIES,
        "papers": records,
    }, ensure_ascii=False))

    u = llm.usage
    cost = (u.prompt_tokens * PRICE_INPUT_CACHE_MISS + u.completion_tokens * PRICE_OUTPUT) / 1e6
    vc = {}
    for r in records:
        vc[r["vetting"]] = vc.get(r["vetting"], 0) + 1
    print(f"完成：{len(records)} 篇 → {OUT}")
    print(f"  靠谱程度分布：{vc}")
    print(f"  本次实际调用 {u.calls - u.cached_calls} 次（缓存 {u.cached_calls} 次），"
          f"按全部用量计成本 ${cost:.2f}")


if __name__ == "__main__":
    main()
