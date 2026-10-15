"""DeepSeek 调用：JSON 输出、磁盘缓存、token 用量统计。"""

import hashlib
import json
import os
import time
from dataclasses import dataclass, field

from openai import OpenAI

from .config import CACHE_DIR, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL, PROMPT_VERSION


@dataclass
class Usage:
    calls: int = 0
    cached_calls: int = 0  # 命中本地磁盘缓存、未实际调用 API 的次数
    prompt_tokens: int = 0
    cache_hit_tokens: int = 0  # DeepSeek 服务端上下文缓存命中的输入 token
    completion_tokens: int = 0
    by_stage: dict = field(default_factory=dict)

    def add(self, stage: str, u: dict) -> None:
        self.calls += 1
        self.prompt_tokens += u["prompt_tokens"]
        self.cache_hit_tokens += u.get("cache_hit_tokens", 0)
        self.completion_tokens += u["completion_tokens"]
        s = self.by_stage.setdefault(stage, {"calls": 0, "prompt_tokens": 0,
                                             "cache_hit_tokens": 0, "completion_tokens": 0})
        s["calls"] += 1
        for k in ("prompt_tokens", "cache_hit_tokens", "completion_tokens"):
            s[k] += u.get(k, 0)


class LLM:
    def __init__(self, model: str = DEEPSEEK_MODEL):
        key = os.environ.get("DEEPSEEK_API_KEY")
        if not key:
            raise SystemExit("请先设置环境变量 DEEPSEEK_API_KEY")
        self.client = OpenAI(api_key=key, base_url=DEEPSEEK_BASE_URL)
        self.model = model
        self.usage = Usage()
        self.cache_dir = CACHE_DIR / "llm"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, stage: str, system: str, user: str):
        h = hashlib.sha256(f"{self.model}|{PROMPT_VERSION}|{stage}|{system}|{user}".encode()).hexdigest()
        return self.cache_dir / f"{stage}_{h[:24]}.json"

    def has_cache(self, stage: str, system: str, user: str) -> bool:
        return self._cache_path(stage, system, user).exists()

    def json_call(self, stage: str, system: str, user: str, max_tokens: int = 1200) -> dict:
        """调用模型并解析 JSON。结果缓存到磁盘，重跑不会重复花钱。

        缓存命中时 token 用量仍按原始调用计入统计，这样成本估算不受重跑影响。
        """
        path = self._cache_path(stage, system, user)
        if path.exists():
            cached = json.loads(path.read_text())
            self.usage.add(stage, cached["usage"])
            self.usage.cached_calls += 1
            return cached["result"]

        last_err: Exception | None = None
        for attempt in range(4):
            try:
                resp = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "system", "content": system},
                              {"role": "user", "content": user}],
                    response_format={"type": "json_object"},
                    temperature=0,
                    max_tokens=max_tokens,
                )
                result = json.loads(resp.choices[0].message.content or "")
                u = resp.usage
                usage = {
                    "prompt_tokens": u.prompt_tokens,
                    "completion_tokens": u.completion_tokens,
                    # DeepSeek 特有字段，其他兼容服务可能没有
                    "cache_hit_tokens": getattr(u, "prompt_cache_hit_tokens", 0) or 0,
                }
                path.write_text(json.dumps({"usage": usage, "result": result}, ensure_ascii=False))
                self.usage.add(stage, usage)
                return result
            except json.JSONDecodeError as e:
                last_err = e  # 输出被截断或格式不对，重试
            except Exception as e:  # 网络 / 限流
                last_err = e
                time.sleep(2 ** attempt * 2)
        raise RuntimeError(f"LLM 调用失败（{stage}）：{last_err}")
