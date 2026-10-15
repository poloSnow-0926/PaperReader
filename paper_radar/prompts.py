"""提示词与输出校验。改动提示词时记得把 config.PROMPT_VERSION 加 1。"""

from .config import (ALGORITHM_FAMILIES, CATEGORIES, COMPUTE_SCALES,
                     REWARD_TYPES, TASK_DOMAINS)

_CAT_LINES = "\n".join(f"- {k}: {v}" for k, v in CATEGORIES.items())

CLASSIFY_SYSTEM = f"""You are a curator for a paper index on **LLM post-training with reinforcement learning / preference optimization**.

A paper is RELEVANT if its main contribution concerns post-training of language models (including vision-language models) via RL, preference optimization, reward modeling, verifiers, or the infrastructure/analysis of these. Examples: RLHF, DPO and variants, GRPO/RLVR for reasoning, process reward models, agentic RL for LLMs, RL training frameworks for LLMs, studies of reward hacking.

NOT relevant: classic RL without language models (robot control, games, offline RL theory), pure pre-training, supervised fine-tuning only (no RL/preference signal), inference-time prompting with no training, general LLM applications.
Exception: a classic RL paper is relevant only if it is a foundational method heavily used in LLM post-training (e.g. PPO, GAE).

Categories (pick exactly one primary, optionally one secondary):
{_CAT_LINES}

Return JSON:
{{"relevant": true|false, "confidence": 0.0-1.0, "primary_category": "<key or null>", "secondary_category": "<key or null>", "reason": "<one short sentence>", "tldr_zh": "<if relevant: one sentence in Simplified Chinese (<= 60 characters): problem, method, key result; else empty string>"}}"""

EXTRACT_SYSTEM = f"""You extract structured facts from an LLM post-training paper for researchers deciding whether the work fits their own training setup.
Only use information stated in the text. If a field is not stated, use "unknown" (or [] for lists). Do not guess.

Fields:
- tldr_zh: one sentence in Simplified Chinese (<= 60 characters): what problem, what method, key result.
- algorithm_family: one of {ALGORITHM_FAMILIES}
- algorithm_name: the paper's own method name, or "unknown"
- reward_type: one of {REWARD_TYPES}
- needs_reward_model: true / false / "unknown" (true if a learned reward model or PRM is trained or used during RL)
- base_models: list of base model names with sizes as written, e.g. ["Qwen2.5-7B", "Llama-3.1-8B-Instruct"]
- max_model_size_b: largest trained model size in billions as a number, or "unknown"
- task_domains: list from {TASK_DOMAINS}
- compute_scale: one of {COMPUTE_SCALES}  (small: <=8 GPUs, medium: 9-63 GPUs, large: >=64 GPUs; "unknown" if GPU count not stated)
- compute_detail: short quote of the hardware statement, or "unknown"
- training_framework: e.g. "verl", "OpenRLHF", "TRL", "DeepSpeed-Chat", "custom", or "unknown"
- open_source: {{"code": true|false|"unknown", "weights": true|false|"unknown", "data": true|false|"unknown"}}

Return a single JSON object with exactly these keys."""


def classify_user(paper: dict) -> str:
    return f"Title: {paper['title']}\n\nAbstract: {paper['abstract']}"


def extract_user(paper: dict, section_text: str | None) -> str:
    body = section_text or f"## Abstract\n{paper['abstract']}\n\n(Full text unavailable; only the abstract is provided.)"
    links = ", ".join(paper.get("github", [])) or "none found"
    return f"Title: {paper['title']}\nGitHub links found in paper: {links}\n\n{body}"


def _enum(value, allowed: list[str], fallback: str) -> str:
    return value if value in allowed else fallback


def _tri(value):
    return value if isinstance(value, bool) else "unknown"


def validate_classification(r: dict) -> dict:
    cats = list(CATEGORIES)
    relevant = bool(r.get("relevant"))
    prim = r.get("primary_category") if r.get("primary_category") in cats else None
    sec = r.get("secondary_category") if r.get("secondary_category") in cats else None
    try:
        conf = float(r.get("confidence", 0))
    except (TypeError, ValueError):
        conf = 0.0
    return {
        "relevant": relevant,
        "confidence": max(0.0, min(1.0, conf)),
        "primary_category": prim if relevant else None,
        "secondary_category": sec if relevant and sec != prim else None,
        "reason": str(r.get("reason", ""))[:300],
        "tldr_zh": str(r.get("tldr_zh") or "")[:200] if relevant else "",
    }


def validate_extraction(r: dict) -> dict:
    size = r.get("max_model_size_b")
    if not isinstance(size, (int, float)) or isinstance(size, bool) or size <= 0:
        size = "unknown"
    os_raw = r.get("open_source") if isinstance(r.get("open_source"), dict) else {}
    domains = r.get("task_domains") if isinstance(r.get("task_domains"), list) else []
    models = r.get("base_models") if isinstance(r.get("base_models"), list) else []
    return {
        "tldr_zh": str(r.get("tldr_zh", ""))[:200],
        "algorithm_family": _enum(r.get("algorithm_family"), ALGORITHM_FAMILIES, "unknown"),
        "algorithm_name": str(r.get("algorithm_name", "unknown"))[:80],
        "reward_type": _enum(r.get("reward_type"), REWARD_TYPES, "unknown"),
        "needs_reward_model": _tri(r.get("needs_reward_model")),
        "base_models": [str(m)[:60] for m in models][:10],
        "max_model_size_b": size,
        "task_domains": [d for d in domains if d in TASK_DOMAINS],
        "compute_scale": _enum(r.get("compute_scale"), COMPUTE_SCALES, "unknown"),
        "compute_detail": str(r.get("compute_detail", "unknown"))[:200],
        "training_framework": str(r.get("training_framework", "unknown"))[:40],
        "open_source": {k: _tri(os_raw.get(k)) for k in ("code", "weights", "data")},
    }
