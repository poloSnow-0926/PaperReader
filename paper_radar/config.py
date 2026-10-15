"""全局配置：模型、细分方向定义、价格等。"""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / ".cache"


def _load_dotenv(path: Path) -> None:
    """读取项目根目录的 .env（KEY=VALUE 格式）。已存在的环境变量优先，不会被覆盖。"""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


_load_dotenv(ROOT / ".env")

# ---- LLM ----
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash-0731")
# 提示词版本：改了 prompt 就加 1，缓存会自动失效
PROMPT_VERSION = 2

# 单价（美元 / 百万 tokens）。按你在 DeepSeek 控制台看到的价格填写，用于估算成本。
# 未填写时只报告 token 用量。
PRICE_INPUT_CACHE_MISS = float(os.environ.get("PRICE_INPUT", "0") or 0)
PRICE_INPUT_CACHE_HIT = float(os.environ.get("PRICE_INPUT_CACHE_HIT", "0") or 0)
PRICE_OUTPUT = float(os.environ.get("PRICE_OUTPUT", "0") or 0)

# 关键章节喂给 LLM 的最大字符数（约 4 字符 ≈ 1 token，2 万字符 ≈ 5k tokens）
MAX_SECTION_CHARS = 20_000

# ---- 细分方向 ----
CATEGORIES: dict[str, str] = {
    "preference_alignment": "偏好对齐：RLHF/PPO、DPO 及变体、Reward Model 训练、AI 反馈",
    "reasoning_rl": "推理强化学习：GRPO、RLVR（可验证奖励）、长思维链（o1/R1 类）",
    "process_reward": "过程奖励 / 验证器：PRM、ORM、生成式验证器",
    "agent_rl": "Agent RL：多轮交互、工具调用、搜索、环境交互",
    "infra": "训练基础设施：verl、OpenRLHF 等 RL 训练框架、rollout/训练效率优化",
    "analysis": "评测与分析：reward hacking、RL 到底教会了模型什么、对齐税等",
}

ALGORITHM_FAMILIES = ["PPO", "GRPO_variant", "DPO_variant", "REINFORCE_variant",
                      "reward_modeling", "other", "unknown"]
REWARD_TYPES = ["verifiable", "learned_rm", "process_rm", "ai_feedback",
                "human_preference", "mixed", "none", "unknown"]
TASK_DOMAINS = ["math", "code", "general_chat", "agent_tools", "safety",
                "multimodal", "other"]
COMPUTE_SCALES = ["small", "medium", "large", "unknown"]  # ≤8 卡 / 9–63 卡 / ≥64 卡
