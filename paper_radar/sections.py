"""从 arXiv HTML 版中抽取关键章节：摘要 + 引言 + 实验设置/训练细节。"""

import re

from bs4 import BeautifulSoup

from .config import MAX_SECTION_CHARS
from .http import request

# 章节标题匹配规则，按优先级排序
_INTRO = re.compile(r"introduction", re.I)
_SETUP = re.compile(
    r"experiment|setup|set-up|implementation|training detail|hyper-?parameter|"
    r"evaluation|settings|reproducib|compute|resources", re.I)
_GITHUB = re.compile(r"https?://github\.com/[\w.-]+/[\w.-]+", re.I)
# arXiv HTML 页面自带的链接（反馈、LaTeXML 转换器），不是论文代码
_GITHUB_BOILERPLATE = re.compile(r"github\.com/(arXiv|brucemiller)/", re.I)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def extract_sections(html: str) -> dict:
    """返回 {"text": 拼接后的章节文本, "sections": 章节标题列表, "github": 链接列表}。"""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup.select("math, .ltx_bibliography, script, style"):
        # 公式的 alttext 已经足够，删除 MathML 结构避免噪音
        if tag.name == "math" and tag.get("alttext"):
            tag.replace_with(f" {tag['alttext']} ")
        else:
            tag.decompose()

    github = sorted({m.group(0).rstrip(".") for m in _GITHUB.finditer(str(soup))
                     if not _GITHUB_BOILERPLATE.search(m.group(0))})

    parts: list[tuple[str, str]] = []
    abstract = soup.select_one(".ltx_abstract")
    if abstract:
        parts.append(("Abstract", _clean(abstract.get_text(" "))))

    intro, setup = [], []
    for sec in soup.select("section.ltx_section, section.ltx_appendix, section.ltx_subsection"):
        title_tag = sec.find(re.compile(r"h[2-4]"), class_="ltx_title")
        if not title_tag:
            continue
        title = _clean(title_tag.get_text(" "))
        if sec.find_parent("section") is not None and "ltx_subsection" not in sec.get("class", []):
            continue
        if _INTRO.search(title) and "ltx_section" in sec.get("class", []):
            intro.append((title, _clean(sec.get_text(" "))))
        elif _SETUP.search(title):
            # 子章节已被父章节包含时跳过
            if any(title in t or _clean(sec.get_text(" "))[:200] in body for t, body in setup):
                continue
            setup.append((title, _clean(sec.get_text(" "))))

    # 预算分配：引言最多 1/3，剩下给实验设置
    budget = MAX_SECTION_CHARS - sum(len(b) for _, b in parts)
    for title, body in intro[:1]:
        chunk = body[: budget // 3]
        parts.append((title, chunk))
        budget -= len(chunk)
    for title, body in setup:
        if budget <= 500:
            break
        chunk = body[:budget]
        parts.append((title, chunk))
        budget -= len(chunk)

    text = "\n\n".join(f"## {t}\n{b}" for t, b in parts)
    return {"text": text, "sections": [t for t, _ in parts], "github": github}


def fetch_sections(arxiv_id: str) -> dict | None:
    """获取 arXiv HTML 版并抽取章节。没有 HTML 版时返回 None（旧论文常见）。"""
    resp = request("GET", f"https://arxiv.org/html/{arxiv_id}")
    if resp.status_code != 200 or "ltx_document" not in resp.text:
        return None
    return extract_sections(resp.text)
