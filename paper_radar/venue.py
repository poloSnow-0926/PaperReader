"""判断论文来源标签：已录用（哪个会议/期刊）/ 预印本 / 技术报告。"""

import re

# 收录的顶会顶刊（规范名 -> 匹配用正则）
TOP_VENUES: dict[str, str] = {
    "NeurIPS": r"neurips|nips|neural information processing systems",
    "ICML": r"\bicml\b|international conference on machine learning",
    "ICLR": r"\biclr\b|international conference on learning representations",
    "ACL": r"\bacl\b|annual meeting of the association for computational linguistics",
    "EMNLP": r"\bemnlp\b|empirical methods in natural language processing",
    "NAACL": r"\bnaacl\b|north american chapter",
    "COLM": r"\bcolm\b|conference on language modeling",
    "AAAI": r"\baaai\b",
    "IJCAI": r"\bijcai\b",
    "TMLR": r"\btmlr\b|transactions on machine learning research",
    "JMLR": r"\bjmlr\b|journal of machine learning research",
    "Nature": r"^nature$|\bnature\b(?! (communications|machine|methods))",
    "Science": r"^science$",
}
_COMPILED = {k: re.compile(v, re.I) for k, v in TOP_VENUES.items()}
_NOT_ACCEPTED = re.compile(r"under review|submitted to|in submission|workshop", re.I)
_ORAL = re.compile(r"\boral\b", re.I)
_SPOTLIGHT = re.compile(r"spotlight", re.I)
_TECH_REPORT = re.compile(r"technical report|tech report", re.I)
_YEAR = re.compile(r"20\d\d")


def match_venue(text: str) -> str | None:
    for name, rx in _COMPILED.items():
        if rx.search(text or ""):
            return name
    return None


def source_label(paper: dict, s2: dict | None = None) -> dict:
    """返回 {"type": published|preprint|tech_report, "venue": str|None, "honor": oral|spotlight|None}。

    优先用 Semantic Scholar 的 venue（权威），其次看 arXiv comment / journal_ref 里写的录用信息。
    """
    comment = f"{paper.get('comment', '')} {paper.get('journal_ref', '')}"
    honor = "oral" if _ORAL.search(comment) else "spotlight" if _SPOTLIGHT.search(comment) else None

    s2_venue = (s2 or {}).get("venue") or ""
    venue = match_venue(s2_venue)
    if not venue and comment.strip() and not _NOT_ACCEPTED.search(comment):
        venue = match_venue(comment)
    if venue:
        year = _YEAR.search(s2_venue) or _YEAR.search(comment)
        return {"type": "published", "venue": f"{venue} {year.group(0)}" if year else venue, "honor": honor}

    if _TECH_REPORT.search(comment) or _TECH_REPORT.search(paper.get("title", "")):
        return {"type": "tech_report", "venue": None, "honor": None}
    return {"type": "preprint", "venue": None, "honor": None}
