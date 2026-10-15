"""把 LLM 结果和你的人工标注对比，按试点通过线输出报告。

labels.csv 填写约定：
  relevant            y / n
  primary_category    细分方向 key（见 paper_radar/config.py 的 CATEGORIES）
  algorithm_family / reward_type / compute_scale   对应枚举值，没写就填 unknown
  needs_reward_model  y / n / unknown
  base_models         用 ; 分隔，如 Qwen2.5-7B;Llama-3.1-8B
  max_model_size_b    数字或 unknown
  task_domains        用 ; 分隔
  tldr_score_1to5     你对一句话总结的打分
留空的单元格不参与统计，所以可以只标一部分字段。

用法：uv run python -m pilot.evaluate
"""

import csv
import json
import re
from pathlib import Path

HERE = Path(__file__).parent

THRESHOLDS = {
    "relevance_acc": 0.90,
    "category_acc": 0.85,
    "key_field_acc": 0.85,
    "key_field_missing": 0.20,  # 上限
    "tldr_score": 4.0,
}
KEY_FIELDS = ["algorithm_family", "reward_type", "base_models", "task_domains"]


def _norm_model(name: str) -> str:
    return re.sub(r"[\s_\-.]", "", name.lower())


def _yn(v: str):
    v = v.strip().lower()
    return {"y": True, "yes": True, "n": False, "no": False}.get(v, "unknown" if v == "unknown" else None)


def field_match(field: str, gold: str, pred) -> bool:
    if field in ("base_models", "task_domains"):
        g = {_norm_model(x) for x in gold.split(";") if x.strip()}
        p = {_norm_model(x) for x in (pred or [])}
        if field == "base_models":
            # 基座模型：只要你标注的每个模型都被抽到即算对（允许 LLM 多列出 instruct 版本等）
            return g <= p if g else not p
        return g == p
    if field == "needs_reward_model":
        return _yn(gold) == pred
    if field == "max_model_size_b":
        if gold.strip().lower() == "unknown":
            return pred == "unknown"
        try:
            return pred != "unknown" and abs(float(gold) - float(pred)) < 0.51
        except ValueError:
            return False
    return gold.strip() == str(pred)


def is_missing(field: str, pred) -> bool:
    return pred in ("unknown", None, [], "")


def main() -> None:
    results = {r["arxiv_id"]: r for r in json.loads((HERE / "results.json").read_text())}
    with open(HERE / "labels.csv", encoding="utf-8-sig") as f:
        labels = list(csv.DictReader(f))

    rel_total = rel_ok = cat_total = cat_ok = 0
    field_stats: dict[str, list[int]] = {}
    missing = missing_total = 0
    tldr_scores: list[float] = []
    errors: list[str] = []

    # 预填过的表（有 checked 列）只统计人工核对过的行，否则就是拿模型和自己比
    prefilled = bool(labels) and "checked" in labels[0]
    n_checked = 0
    for row in labels:
        r = results.get(row["arxiv_id"])
        if r is None:
            continue
        if prefilled and row.get("checked", "").strip().lower() not in ("y", "yes"):
            continue
        n_checked += 1
        cls = r["classification"]
        gold_rel = _yn(row.get("relevant", ""))
        if isinstance(gold_rel, bool):
            rel_total += 1
            if gold_rel == cls["relevant"]:
                rel_ok += 1
            else:
                errors.append(f"[相关性] {row['arxiv_id']} 标注={gold_rel} 预测={cls['relevant']}  {row['title'][:60]}")

        if gold_rel and row.get("primary_category", "").strip():
            cat_total += 1
            gold_cat = row["primary_category"].strip()
            # 主方向对上，或你的主方向是 LLM 给出的次方向，都算对
            if gold_cat in (cls["primary_category"], cls["secondary_category"]):
                cat_ok += 1
            else:
                errors.append(f"[方向] {row['arxiv_id']} 标注={gold_cat} 预测={cls['primary_category']}")

        ext = r.get("extraction")
        if not (gold_rel and ext):
            continue
        for field in ["algorithm_family", "reward_type", "needs_reward_model", "base_models",
                      "max_model_size_b", "task_domains", "compute_scale"]:
            gold = row.get(field, "").strip()
            if field in KEY_FIELDS:
                missing_total += 1
                missing += is_missing(field, ext[field])
            if not gold:
                continue
            ok = field_match(field, gold, ext[field])
            s = field_stats.setdefault(field, [0, 0])
            s[0] += ok
            s[1] += 1
            if not ok:
                errors.append(f"[{field}] {row['arxiv_id']} 标注={gold} 预测={ext[field]}")
        if row.get("tldr_score_1to5", "").strip():
            tldr_scores.append(float(row["tldr_score_1to5"]))

    def rate(a: int, b: int):
        return a / b if b else None

    key_ok = sum(field_stats.get(f, [0, 0])[0] for f in KEY_FIELDS)
    key_n = sum(field_stats.get(f, [0, 0])[1] for f in KEY_FIELDS)
    metrics = {
        "relevance_acc": (rate(rel_ok, rel_total), rel_total),
        "category_acc": (rate(cat_ok, cat_total), cat_total),
        "key_field_acc": (rate(key_ok, key_n), key_n),
        "key_field_missing": (rate(missing, missing_total), missing_total),
        "tldr_score": (sum(tldr_scores) / len(tldr_scores) if tldr_scores else None, len(tldr_scores)),
    }

    print("=== 试点评估 ===")
    print(f"  参与统计 {n_checked} 篇" + ("（仅 checked=y 的行）" if prefilled else ""))
    all_pass = True
    for k, (v, n) in metrics.items():
        th = THRESHOLDS[k]
        if v is None:
            print(f"  {k:20s} 无标注数据")
            all_pass = False
            continue
        passed = v <= th if k == "key_field_missing" else v >= th
        all_pass &= passed
        shown = f"{v:.2f}" if k == "tldr_score" else f"{v:.1%}"
        op = "≤" if k == "key_field_missing" else "≥"
        print(f"  {k:20s} {shown:>7s}  (n={n}, 通过线 {op} {th})  {'✓' if passed else '✗'}")

    print("\n各字段准确率：")
    for f, (ok, n) in field_stats.items():
        print(f"  {f:20s} {ok}/{n} = {ok / n:.0%}")

    usage = HERE / "usage.json"
    if usage.exists():
        est = json.loads(usage.read_text())["full_run_estimate"]
        c = est.get("cost_usd")
        print(f"\n全量成本估算：{'$%.2f' % c if c is not None else '未设置单价'}（通过线 ≤ $35）")
        if c is not None:
            all_pass &= c <= 35

    print(f"\n结论：{'通过，可以跑全量' if all_pass else '未通过，看下面的错误样例调整 prompt'}")
    if errors:
        print(f"\n错误样例（共 {len(errors)} 条，最多显示 40 条）：")
        for e in errors[:40]:
            print("  " + e)


if __name__ == "__main__":
    main()
