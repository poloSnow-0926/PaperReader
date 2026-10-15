"""构建 100 篇试点样本，并生成供人工标注的 CSV。

样本 = 种子论文（已知重要工作）+ 各细分方向的 arXiv 检索结果 + 约 20 篇干扰项。
输出：
  pilot/sample.json      论文元数据（流水线输入）
  pilot/labels.csv       人工标注表（你来填写"标准答案"）

用法：uv run python -m pilot.build_sample
"""

import csv
import json
import random
from pathlib import Path

from paper_radar import arxiv

HERE = Path(__file__).parent
TARGET_RELEVANT = 80
TARGET_DISTRACTOR = 20
DATE_FILTER = "submittedDate:[202410150000 TO 202610142359]"  # 近两年

# 奠基 / 必读种子（含少量早于两年的经典），保证样本里有一批你能凭经验判断的论文
SEEDS = [
    "1707.06347",  # PPO
    "2203.02155",  # InstructGPT
    "2212.08073",  # Constitutional AI
    "2305.18290",  # DPO
    "2305.20050",  # Let's Verify Step by Step (PRM800K)
    "2312.08935",  # Math-Shepherd
    "2402.01306",  # KTO
    "2402.03300",  # DeepSeekMath (GRPO)
    "2405.11143",  # OpenRLHF
    "2405.14734",  # SimPO
    "2409.19256",  # HybridFlow / verl
    "2411.15124",  # Tulu 3
    "2501.12599",  # Kimi k1.5
    "2501.12948",  # DeepSeek-R1
    "2503.09516",  # Search-R1
    "2503.14476",  # DAPO
    "2503.20783",  # Understanding R1-Zero-Like Training (Dr. GRPO)
]

# 每个细分方向的检索式（arXiv API 语法）
CATEGORY_QUERIES = {
    "preference_alignment": 'abs:"direct preference optimization" OR abs:RLHF',
    "reasoning_rl": 'abs:"verifiable rewards" OR abs:GRPO',
    "process_reward": 'abs:"process reward model"',
    "agent_rl": 'abs:"reinforcement learning" AND abs:agent AND abs:"tool"  AND abs:LLM',
    "infra": 'abs:"reinforcement learning" AND abs:rollout AND abs:throughput AND abs:LLM',
    "analysis": 'abs:"reward hacking" OR abs:"does reinforcement learning really"',
}

# 看起来相关但不该收录的干扰项
DISTRACTOR_QUERIES = [
    'abs:"reinforcement learning" AND abs:robot AND abs:locomotion',
    'abs:"offline reinforcement learning" AND abs:"value function"',
    'abs:"multi-agent reinforcement learning" AND abs:game',
    'abs:"pre-training" AND abs:"language model" AND abs:"data mixture"',
    'abs:"supervised fine-tuning" AND abs:"instruction tuning" AND abs:dataset',
]


def _search_dated(query: str, n: int) -> list[dict]:
    return arxiv.search(f"({query}) AND {DATE_FILTER}", max_results=n)


def main() -> None:
    random.seed(42)
    papers: dict[str, dict] = {}
    origin: dict[str, str] = {}

    print("获取种子论文…")
    for p in arxiv.fetch_by_ids(SEEDS):
        papers[p["arxiv_id"]] = p
        origin[p["arxiv_id"]] = "seed"

    per_cat = (TARGET_RELEVANT - len(papers)) // len(CATEGORY_QUERIES) + 1
    for cat, q in CATEGORY_QUERIES.items():
        print(f"检索 {cat}…")
        hits = [p for p in _search_dated(q, 40) if p["arxiv_id"] not in papers]
        for p in random.sample(hits, min(per_cat, len(hits))):
            papers[p["arxiv_id"]] = p
            origin[p["arxiv_id"]] = f"query:{cat}"

    per_d = TARGET_DISTRACTOR // len(DISTRACTOR_QUERIES)
    for q in DISTRACTOR_QUERIES:
        print(f"检索干扰项 {q[:40]}…")
        hits = [p for p in _search_dated(q, 30) if p["arxiv_id"] not in papers]
        for p in random.sample(hits, min(per_d, len(hits))):
            papers[p["arxiv_id"]] = p
            origin[p["arxiv_id"]] = "distractor"

    sample = list(papers.values())
    for p in sample:
        p["sample_origin"] = origin[p["arxiv_id"]]
    (HERE / "sample.json").write_text(json.dumps(sample, ensure_ascii=False, indent=1))

    # 人工标注表：留空的列由你填写
    cols = ["arxiv_id", "title", "sample_origin", "relevant", "primary_category",
            "algorithm_family", "reward_type", "needs_reward_model", "base_models",
            "max_model_size_b", "task_domains", "compute_scale", "tldr_score_1to5", "notes"]
    with open(HERE / "labels.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for p in sample:
            w.writerow({"arxiv_id": p["arxiv_id"], "title": p["title"],
                        "sample_origin": p["sample_origin"]})

    n_d = sum(1 for p in sample if p["sample_origin"] == "distractor")
    print(f"完成：共 {len(sample)} 篇（干扰项 {n_d} 篇）→ pilot/sample.json, pilot/labels.csv")


if __name__ == "__main__":
    main()
