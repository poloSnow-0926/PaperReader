"""Semantic Scholar：引用数、高影响力引用、发表会议。

结果按论文缓存 7 天：被限流跳过的论文下次运行会补上，已成功的不再重复请求。
"""

import json
import os
import time

from .config import CACHE_DIR
from .http import request

BATCH_URL = "https://api.semanticscholar.org/graph/v1/paper/batch"
FIELDS = "title,year,venue,publicationVenue,publicationTypes,citationCount,influentialCitationCount,externalIds"
CACHE_TTL = 7 * 24 * 3600
_CACHE = CACHE_DIR / "s2.json"


def _load_cache() -> dict:
    if _CACHE.exists():
        return json.loads(_CACHE.read_text())
    return {}


def _save_cache(cache: dict) -> None:
    _CACHE.parent.mkdir(parents=True, exist_ok=True)
    _CACHE.write_text(json.dumps(cache, ensure_ascii=False))


def fetch_batch(arxiv_ids: list[str]) -> dict[str, dict]:
    """返回 {arxiv_id: s2 数据}。未找到或被限流的论文不在结果里。

    没有 API key 时 S2 限流很严，建议设置环境变量 S2_API_KEY（免费申请）。
    """
    headers = {}
    if key := os.environ.get("S2_API_KEY"):
        headers["x-api-key"] = key

    cache = _load_cache()
    now = time.time()
    fresh = {a: cache[a] for a in arxiv_ids if a in cache and now - cache[a]["fetched_at"] < CACHE_TTL}
    todo = [a for a in arxiv_ids if a not in fresh]

    failed = 0
    for i in range(0, len(todo), 100):
        chunk = todo[i:i + 100]
        resp = request("POST", BATCH_URL, params={"fields": FIELDS},
                       json={"ids": [f"ARXIV:{a}" for a in chunk]}, headers=headers, retries=8)
        if resp.status_code != 200:
            failed += len(chunk)
            print(f"  [S2] 批量请求失败 HTTP {resp.status_code}，跳过 {len(chunk)} 篇（下次运行会重试）")
            continue
        for aid, item in zip(chunk, resp.json()):
            # 没找到的论文也记入缓存（data=None），避免每次都重复查
            cache[aid] = {"fetched_at": now, "data": item and {
                "citation_count": item.get("citationCount"),
                "influential_citation_count": item.get("influentialCitationCount"),
                "venue": item.get("venue") or (item.get("publicationVenue") or {}).get("name", ""),
                "year": item.get("year"),
                "publication_types": item.get("publicationTypes") or [],
            }}
            fresh[aid] = cache[aid]
        _save_cache(cache)
        time.sleep(1.1)

    if failed and not headers:
        print("  [S2] 提示：未设置 S2_API_KEY，免费申请：https://www.semanticscholar.org/product/api#api-key-form")
    return {a: v["data"] for a, v in fresh.items() if v["data"]}
