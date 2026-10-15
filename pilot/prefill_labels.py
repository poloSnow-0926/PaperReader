"""用 LLM 结果预填 labels.csv，人工只需核对、改错，并在 checked 列填 y。

注意：评估只统计 checked=y 的行。没核对的行等于拿模型和自己比，没有意义。

用法：uv run python -m pilot.prefill_labels
"""

import csv
import json
from pathlib import Path

HERE = Path(__file__).parent
LABELS = HERE / "labels.csv"

LABEL_COLS = ["relevant", "primary_category", "algorithm_family", "reward_type",
              "needs_reward_model", "base_models", "max_model_size_b", "task_domains",
              "compute_scale", "tldr_score_1to5", "notes"]
# 只读参考列：帮你快速判断，不参与评估
EVIDENCE_COLS = ["url", "llm_reason", "tldr_zh", "compute_detail", "sections_used"]
COLS = ["checked", "arxiv_id", "title", "sample_origin", *LABEL_COLS, *EVIDENCE_COLS]


def _yn(v) -> str:
    return {True: "y", False: "n"}.get(v, "unknown")


def _already_labeled() -> bool:
    if not LABELS.exists():
        return False
    with open(LABELS, encoding="utf-8-sig") as f:
        return any((row.get(c) or "").strip()
                   for row in csv.DictReader(f) for c in ["checked", *LABEL_COLS])


def main() -> None:
    if _already_labeled():
        raise SystemExit("labels.csv 里已有填写内容，为避免覆盖已停止。需要重新预填请先删除或改名该文件。")

    results = json.loads((HERE / "results.json").read_text())
    with open(LABELS, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        for r in results:
            cls = r["classification"]
            ext = r.get("extraction") or {}
            row = {
                "checked": "",
                "arxiv_id": r["arxiv_id"],
                "title": r["title"],
                "sample_origin": r["sample_origin"],
                "relevant": _yn(cls["relevant"]),
                "primary_category": cls["primary_category"] or "",
                "url": f"https://arxiv.org/abs/{r['arxiv_id']}",
                "llm_reason": cls["reason"],
            }
            if ext:
                row.update({
                    "algorithm_family": ext["algorithm_family"],
                    "reward_type": ext["reward_type"],
                    "needs_reward_model": _yn(ext["needs_reward_model"]),
                    "base_models": ";".join(ext["base_models"]),
                    "max_model_size_b": ext["max_model_size_b"],
                    "task_domains": ";".join(ext["task_domains"]),
                    "compute_scale": ext["compute_scale"],
                    "tldr_zh": ext["tldr_zh"],
                    "compute_detail": ext["compute_detail"],
                    "sections_used": " | ".join(r.get("sections_used", [])),
                })
            w.writerow(row)
    print(f"已预填 {len(results)} 行 → {LABELS}")
    print("逐行核对，改错后在 checked 列填 y；tldr_score_1to5 需要你自己打分。")


if __name__ == "__main__":
    main()
