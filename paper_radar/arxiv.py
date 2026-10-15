"""arXiv API：按 ID 或关键词获取论文元数据。"""

import re
import time

from bs4 import BeautifulSoup

from .http import request

API = "https://export.arxiv.org/api/query"
_last_call = 0.0


def _throttle() -> None:
    # arXiv 要求每 3 秒最多 1 次请求
    global _last_call
    wait = 3.1 - (time.time() - _last_call)
    if wait > 0:
        time.sleep(wait)
    _last_call = time.time()


def normalize_id(raw: str) -> str:
    """'http://arxiv.org/abs/2503.14476v2' -> '2503.14476'"""
    raw = raw.strip().rsplit("/abs/", 1)[-1]
    return re.sub(r"v\d+$", "", raw)


def parse_feed(xml: str) -> list[dict]:
    soup = BeautifulSoup(xml, "xml")
    papers = []
    for entry in soup.find_all("entry"):
        id_tag = entry.find("id")
        if id_tag is None or "/abs/" not in id_tag.text:
            continue  # 错误条目
        def text(tag: str) -> str:
            t = entry.find(tag)
            return " ".join(t.text.split()) if t else ""
        journal = entry.find("journal_ref")
        comment = entry.find("comment")
        papers.append({
            "arxiv_id": normalize_id(id_tag.text),
            "title": text("title"),
            "abstract": text("summary"),
            "authors": [" ".join(a.find("name").text.split()) for a in entry.find_all("author")],
            "published": text("published")[:10],
            "categories": [c["term"] for c in entry.find_all("category")],
            "journal_ref": " ".join(journal.text.split()) if journal else "",
            "comment": " ".join(comment.text.split()) if comment else "",
        })
    return papers


def fetch_by_ids(ids: list[str]) -> list[dict]:
    results = []
    for i in range(0, len(ids), 50):
        _throttle()
        resp = request("GET", API, params={"id_list": ",".join(ids[i:i + 50]), "max_results": 50})
        resp.raise_for_status()
        results.extend(parse_feed(resp.text))
    return results


def search(query: str, max_results: int = 50, start: int = 0) -> list[dict]:
    _throttle()
    resp = request("GET", API, params={
        "search_query": query, "start": start, "max_results": max_results,
        "sortBy": "relevance", "sortOrder": "descending",
    })
    resp.raise_for_status()
    return parse_feed(resp.text)
