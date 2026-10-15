"""按月从 arXiv 抓取候选论文（关键词初筛），结果按月缓存。"""

import json
import re
from datetime import date

from . import arxiv
from .config import CACHE_DIR
from .http import request

# 初筛：RL/偏好相关词 AND 语言模型相关词。宁宽勿严，后面由 LLM 判断相关性
HARVEST_QUERY = (
    '(abs:"reinforcement learning" OR abs:RLHF OR abs:"preference optimization" OR abs:DPO '
    'OR abs:GRPO OR abs:"reward model" OR abs:"reward models" OR abs:"verifiable reward" '
    'OR abs:"verifiable rewards" OR abs:"process reward" OR abs:"policy optimization") '
    'AND (abs:"language model" OR abs:"language models" OR abs:LLM OR abs:LLMs)'
)
PAGE = 200
_CACHE = CACHE_DIR / "harvest"


def months_between(start: date, end: date) -> list[tuple[int, int]]:
    out, y, m = [], start.year, start.month
    while (y, m) <= (end.year, end.month):
        out.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def _month_range(y: int, m: int) -> str:
    ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
    return f"submittedDate:[{y}{m:02d}010000 TO {ny}{nm:02d}010000]"


def harvest_month(y: int, m: int, refresh: bool = False) -> list[dict]:
    """抓取某月全部候选。已结束的月份读缓存；当月（或 refresh=True）重新抓。"""
    _CACHE.mkdir(parents=True, exist_ok=True)
    path = _CACHE / f"{y}{m:02d}.json"
    today = date.today()
    is_current = (y, m) == (today.year, today.month)
    if path.exists() and not refresh and not is_current:
        return json.loads(path.read_text())

    query = f"({HARVEST_QUERY}) AND {_month_range(y, m)}"
    papers: dict[str, dict] = {}
    total = None
    start = 0
    while total is None or start < total:
        arxiv._throttle()
        resp = request("GET", arxiv.API, params={
            "search_query": query, "start": start, "max_results": PAGE,
            "sortBy": "submittedDate", "sortOrder": "ascending",
        })
        resp.raise_for_status()
        if total is None:
            mt = re.search(r"totalResults[^>]*>(\d+)", resp.text)
            total = int(mt.group(1)) if mt else 0
        batch = arxiv.parse_feed(resp.text)
        if not batch:
            break  # arXiv 偶尔返回空页，避免死循环
        for p in batch:
            papers[p["arxiv_id"]] = p
        start += PAGE

    result = list(papers.values())
    path.write_text(json.dumps(result, ensure_ascii=False))
    return result
