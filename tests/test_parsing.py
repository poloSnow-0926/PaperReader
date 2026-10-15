from paper_radar import arxiv, prompts
from paper_radar.sections import extract_sections
from paper_radar.venue import source_label

FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
<entry>
  <id>http://arxiv.org/abs/2503.14476v2</id>
  <published>2025-03-18T17:49:06Z</published>
  <title>DAPO: An Open-Source LLM
   Reinforcement Learning System at Scale</title>
  <summary>We propose DAPO.</summary>
  <author><name>Qiying Yu</name></author>
  <arxiv:comment>Accepted to NeurIPS 2025 (Oral)</arxiv:comment>
  <category term="cs.LG"/>
</entry>
</feed>"""


def test_parse_feed():
    [p] = arxiv.parse_feed(FEED)
    assert p["arxiv_id"] == "2503.14476"
    assert p["title"] == "DAPO: An Open-Source LLM Reinforcement Learning System at Scale"
    assert p["comment"] == "Accepted to NeurIPS 2025 (Oral)"


def test_source_label():
    assert source_label({"comment": "Accepted to NeurIPS 2025 (Oral)"}) == \
        {"type": "published", "venue": "NeurIPS 2025", "honor": "oral"}
    assert source_label({"comment": "Under review at ICLR 2026"})["type"] == "preprint"
    assert source_label({"comment": "", "title": "Kimi k1.5 Technical Report"})["type"] == "tech_report"
    assert source_label({"comment": ""}, {"venue": "International Conference on Learning Representations"})["venue"] == "ICLR"
    assert source_label({"comment": ""}, {"venue": "Nature Communications"})["type"] == "preprint"


def test_extract_sections():
    html = """<html><body><div class="ltx_document">
    <div class="ltx_abstract">An abstract.</div>
    <section class="ltx_section"><h2 class="ltx_title">1 Introduction</h2><p>Intro text.</p></section>
    <section class="ltx_section"><h2 class="ltx_title">2 Related Work</h2><p>Skip me.</p></section>
    <section class="ltx_section"><h2 class="ltx_title">4 Experimental Setup</h2>
      <p>We train Qwen2.5-7B on 8 H100 GPUs. Code: https://github.com/foo/bar.</p></section>
    </div></body></html>"""
    out = extract_sections(html)
    assert out["sections"] == ["Abstract", "1 Introduction", "4 Experimental Setup"]
    assert "Skip me" not in out["text"]
    assert out["github"] == ["https://github.com/foo/bar"]


def test_validate_extraction_rejects_bad_values():
    r = prompts.validate_extraction({"algorithm_family": "MagicRL", "max_model_size_b": "7B",
                                     "needs_reward_model": "yes", "task_domains": ["math", "poetry"]})
    assert r["algorithm_family"] == "unknown"
    assert r["max_model_size_b"] == "unknown"
    assert r["needs_reward_model"] == "unknown"
    assert r["task_domains"] == ["math"]


def test_validate_classification_drops_category_when_irrelevant():
    r = prompts.validate_classification({"relevant": False, "primary_category": "infra", "confidence": 3})
    assert r["primary_category"] is None and r["confidence"] == 1.0
