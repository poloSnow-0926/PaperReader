# Paper Radar：LLM 后训练论文索引

按细分方向收录近两年 LLM 后训练 / 强化学习论文（arXiv + 顶会录用信息 + 引用数据），
并在浏览器本地管理自己的阅读状态、评分和笔记。

> 状态：项目已暂停。`web/public/papers.json` 是部分数据：2024-11 至 2026-10 的候选中，
> 已完成 LLM 分类的 3071 篇里有 2251 篇判定为相关。没有引用数据（Semantic Scholar key 未获批）。

## 本地使用

```bash
cp .env.example .env        # 填写中转站地址、API key、单价
uv sync

# 抓取 + 分类，输出 web/public/papers.json
uv run python -m paper_radar.build --dry-run     # 只抓取并估算成本
uv run python -m paper_radar.build --months 1    # 只跑最近 1 个月
uv run python -m paper_radar.build               # 近两年全量

cd web && npm install && npm run dev             # 打开 http://localhost:5173
```

LLM 结果缓存在 `.cache/`，重跑不会重复计费；已结束月份的 arXiv 抓取结果也会缓存。
修改 prompt 后把 `paper_radar/config.py` 里的 `PROMPT_VERSION` 加 1。

## 收录与"靠谱"规则

- 候选：arXiv 摘要同时包含 RL/偏好优化类关键词和语言模型类关键词
- 相关性和细分方向：DeepSeek 根据标题和摘要判断，同时生成一句话中文总结
- 默认只显示"靠谱"的论文：种子必读、已被顶会顶刊录用、技术报告、月均引用 ≥ 1，或发布不满 60 天的新论文。取消勾选"只看靠谱的"可以看全部

## 个人数据

阅读状态、评分、笔记只存在浏览器 localStorage。换浏览器或清缓存前，用页面右上角的"导出我的数据"备份。

## 部署

在线访问：https://polosnow-0926.github.io/PaperReader/

每次推送到 `main`，`.github/workflows/update.yml` 会用仓库里的 `web/public/papers.json` 构建前端并部署到 GitHub Pages，不调用任何 API。
首次需要在仓库 Settings → Pages 里把 Source 设为 "GitHub Actions"。

## 试点（已完成）

`pilot/` 下是 100 篇样本的准确率与成本试点脚本，见 `pilot/evaluate.py`。
