"""对试点样本跑完整流水线：S2 引用 → 来源标签 → LLM 分类 → 章节解析 → LLM 字段抽取。

输出：
  pilot/results.json   每篇论文的全部结果
  pilot/usage.json     token 用量与成本推算

用法：
  export DEEPSEEK_API_KEY=...
  # 可选：填入单价（美元/百万 tokens）以计算成本
  export PRICE_INPUT=... PRICE_INPUT_CACHE_HIT=... PRICE_OUTPUT=...
  uv run python -m pilot.run_pilot
"""

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from paper_radar import prompts, semantic_scholar, sections
from paper_radar.config import (DEEPSEEK_MODEL, PRICE_INPUT_CACHE_HIT,
                                PRICE_INPUT_CACHE_MISS, PRICE_OUTPUT)
from paper_radar.llm import LLM
from paper_radar.venue import source_label

HERE = Path(__file__).parent
# 全量规模假设（用于推算）：关键词初筛后的候选数、其中相关并需要抽取的篇数
FULL_CANDIDATES = 15_000
FULL_RELEVANT = 4_000


def process(llm: LLM, paper: dict, s2: dict | None) -> dict:
    result = {**paper, "s2": s2, "source": source_label(paper, s2)}

    cls = prompts.validate_classification(
        llm.json_call("classify", prompts.CLASSIFY_SYSTEM, prompts.classify_user(paper), max_tokens=300))
    result["classification"] = cls
    if not cls["relevant"]:
        return result

    sec = sections.fetch_sections(paper["arxiv_id"])
    result["sections_used"] = sec["sections"] if sec else ["Abstract (no HTML)"]
    result["github"] = sec["github"] if sec else []
    paper_for_prompt = {**paper, "github": result["github"]}
    raw = llm.json_call("extract", prompts.EXTRACT_SYSTEM,
                        prompts.extract_user(paper_for_prompt, sec["text"] if sec else None))
    result["extraction"] = prompts.validate_extraction(raw)
    return result


def cost(prompt_tokens: int, hit_tokens: int, completion_tokens: int) -> float | None:
    if not (PRICE_INPUT_CACHE_MISS or PRICE_OUTPUT):
        return None
    miss = prompt_tokens - hit_tokens
    return (miss * PRICE_INPUT_CACHE_MISS + hit_tokens * PRICE_INPUT_CACHE_HIT
            + completion_tokens * PRICE_OUTPUT) / 1e6


def main() -> None:
    sample = json.loads((HERE / "sample.json").read_text())
    print(f"样本 {len(sample)} 篇，模型 {DEEPSEEK_MODEL}")

    print("获取 Semantic Scholar 引用数据…")
    s2 = semantic_scholar.fetch_batch([p["arxiv_id"] for p in sample])
    print(f"  S2 命中 {len(s2)}/{len(sample)}")

    llm = LLM()
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(process, llm, p, s2.get(p["arxiv_id"])) for p in sample]
        results = []
        for i, f in enumerate(futures, 1):
            try:
                results.append(f.result())
            except Exception as e:
                print(f"  失败 {sample[i - 1]['arxiv_id']}: {e}")
            if i % 10 == 0:
                print(f"  {i}/{len(sample)}")

    (HERE / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=1))

    # ---- 用量与全量推算 ----
    u = llm.usage
    stages = u.by_stage
    c = stages.get("classify", {"calls": 0, "prompt_tokens": 0, "cache_hit_tokens": 0, "completion_tokens": 0})
    e = stages.get("extract", {"calls": 0, "prompt_tokens": 0, "cache_hit_tokens": 0, "completion_tokens": 0})

    def per_call(s: dict, k: str) -> float:
        return s[k] / s["calls"] if s["calls"] else 0

    full = {k: per_call(c, k) * FULL_CANDIDATES + per_call(e, k) * FULL_RELEVANT
            for k in ("prompt_tokens", "cache_hit_tokens", "completion_tokens")}
    report = {
        "model": DEEPSEEK_MODEL,
        "pilot": {"papers": len(results), "failed": len(sample) - len(results), **u.by_stage,
                  "cost_usd": cost(u.prompt_tokens, u.cache_hit_tokens, u.completion_tokens)},
        "avg_tokens_per_call": {
            "classify": {k: round(per_call(c, k)) for k in ("prompt_tokens", "completion_tokens")},
            "extract": {k: round(per_call(e, k)) for k in ("prompt_tokens", "completion_tokens")},
        },
        "full_run_estimate": {
            "assumption": f"{FULL_CANDIDATES} 篇候选分类 + {FULL_RELEVANT} 篇字段抽取",
            **{k: round(v) for k, v in full.items()},
            "cost_usd": cost(full["prompt_tokens"], full["cache_hit_tokens"], full["completion_tokens"]),
        },
    }
    (HERE / "usage.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))

    print("\n=== 用量 ===")
    print(json.dumps(report, ensure_ascii=False, indent=1))
    if report["pilot"]["cost_usd"] is None:
        print("\n未设置 PRICE_INPUT / PRICE_OUTPUT，只报告了 token 数。")
    print("\n下一步：填写 pilot/labels.csv，然后运行 uv run python -m pilot.evaluate")


if __name__ == "__main__":
    main()
