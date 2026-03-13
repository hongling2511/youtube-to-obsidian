# YouTube → NotebookLM → Obsidian 知识管道

## 项目概述

自动化管道：YouTube URL → yt-dlp 元数据 → notebooklm-py 深度分析 → 结构化 Markdown 写入 Obsidian Vault。

**技术栈**：Python 3.12 + uv + yt-dlp + notebooklm-py + click + pyyaml
**Obsidian Vault**：`/Users/hongling/obsidian`（PARA 方法组织）

## 架构决策

- **路径 A 优先**：NotebookLM 直接处理 YouTube URL（`sources.add_url()`）
- **路径 B 兜底**：yt-dlp 提取字幕 → 作为文本上传（`sources.add_text()`）
- **语言**：中文为主，保留英文术语原文
- **实现节奏**：逐 Phase 推进，每 Phase 验证通过后再进下一阶段

## 项目结构

```
youtube-to-obsidian/
├── pyproject.toml          # uv 管理依赖
├── config.yaml             # 运行时配置
├── main.py                 # CLI 入口（click）
├── src/
│   ├── __init__.py
│   ├── extractor.py        # yt-dlp 元数据 & 字幕提取
│   ├── analyzer.py         # notebooklm-py 分析引擎
│   ├── generator.py        # Markdown 生成 + Obsidian 写入
│   └── pipeline.py         # 流程编排 + SQLite 去重
├── prompts/
│   ├── core.txt            # 核心分析 prompt
│   ├── concepts.txt        # 关键概念提取 prompt（Phase 2）
│   └── actions.txt         # 行动项提取 prompt（Phase 2）
├── processed.db            # SQLite 处理记录（自动创建）
└── output/                 # 临时文件（mindmap/quiz json）
```

## Obsidian Vault 结构（PARA）

```
/Users/hongling/obsidian/
├── 0-收集箱/               # Pipeline 笔记自动写入此处
├── 1-项目/
├── 2-领域/
├── 3-资源/
│   └── YouTube/
│       ├── 技术教程/
│       ├── 播客访谈/
│       ├── 知识科普/
│       └── 行业分析/
├── 4-归档/
├── MOC/                    # Map of Content 导航枢纽
├── _模板/
├── _附件/
│   ├── mindmaps/           # NotebookLM 生成的思维导图 JSON
│   └── quizzes/            # NotebookLM 生成的测验
└── _转录/                  # 原始转录文本存档（可选）
```

## 实现路线图

### Phase 1：环境 + MVP ✅当前阶段

目标：跑通 "一个 URL → 一篇 Obsidian 笔记" 完整链路。

#### Step 1：项目初始化 + 依赖安装

```bash
cd /Users/hongling
uv init youtube-to-obsidian --python 3.12
cd youtube-to-obsidian
uv add yt-dlp "notebooklm-py[browser]" click pyyaml
```

#### Step 2：Obsidian Vault 目录初始化

创建 PARA 骨架目录结构。

#### Step 3：config.yaml

```yaml
obsidian:
  vault_path: "/Users/hongling/obsidian"
  inbox_folder: "0-收集箱"

youtube:
  preferred_languages: ["zh", "en"]

notebooklm:
  generate_quiz: false       # MVP 关闭
  generate_mindmap: false    # MVP 关闭
  generate_audio: false
  cleanup_notebook: true     # 处理完后删除 Notebook
  quiz_min_duration: 600

db_path: "./processed.db"
```

#### Step 4：extractor.py

两个核心函数：

**`get_video_metadata(url) -> dict`**
- 调用 `yt-dlp --dump-json --no-download`
- 返回：video_id, title, channel, channel_url, upload_date, duration, duration_string, description, tags, categories, language, chapters, thumbnail, view_count, url

**`extract_transcript(url, langs) -> str | None`**（路径 B 兜底）
- 调用 `yt-dlp --write-sub --write-auto-sub --sub-lang zh,en --sub-format vtt --skip-download`
- 优先人工字幕 > 自动字幕
- `parse_vtt_to_text()` 去重复行、去 HTML 标签

#### Step 5：analyzer.py

**`analyze_video(url, metadata, config) -> dict`**

```python
async def analyze_video(url, metadata, config):
    async with NotebookLMClient(...) as client:
        # 1. 创建 Notebook
        nb = await client.notebooks.create(f"YT: {metadata['title'][:80]}")

        # 2. 添加源（路径 A 优先）
        try:
            await client.sources.add_url(nb.id, url)
        except Exception:
            transcript = extract_transcript(url, config["youtube"]["preferred_languages"])
            if not transcript:
                raise ValueError("无法获取视频内容")
            await client.sources.add_text(nb.id, transcript, title=metadata["title"])

        # 3. 核心分析
        result = await client.chat.ask(nb.id, load_prompt("core"))

        # 4. 可选：清理 Notebook
        if config["notebooklm"]["cleanup_notebook"]:
            await client.notebooks.delete(nb.id)

        return {"core": result.answer, "notebook_id": nb.id}
```

**注意**：notebooklm-py 的实际 API 初始化方式需以安装后的文档为准（`from_storage()` vs 直接构造），实现时先确认：
```bash
uv run python -c "import notebooklm; help(notebooklm)"
```

#### Step 6：prompts/core.txt

```
请对这个视频内容做结构化分析，用中文回答，保留英文术语原文。

要求：
- 严格按固定标题输出，不要添加额外小节
- 信息不足时明确写「未明确提及」，不要猜测
- 仅对关键概念使用 [[双向链接]]

## 一句话总结
（不超过 30 个字）

## 内容类型
（只输出：tech_tutorial / podcast / knowledge / business）

## 目标受众与前置知识
（说明适合谁看，以及需要的背景知识）

## 核心观点
（列出 3-5 个最重要的观点，每个观点包含概括、重要性、依据）

## 详细笔记
（按视频逻辑整理结构化笔记；不强制时间戳）

## 金句亮点
（提取 2-3 句最有价值的原意表达；必要时可标注「意译」）

## 适用场景与行动建议
（说明适用场景和 1-3 个可执行行动）

## 价值评分
（1-5 分，从信息密度、实用性、新颖性三个维度打分）
```

#### Step 7：generator.py

**`generate_obsidian_note(metadata, analysis, config) -> Path`**

生成结构：
```markdown
---
type: youtube
title: "视频标题"
channel: "[[频道名]]"
url: https://youtube.com/watch?v=xxx
video_id: xxx
date_watched: 2026-03-12
date_published: 2026-03-01
duration: "1:23:45"
tags:
  - tag1
  - tag2
---

# 视频标题

{core analysis 内容}

---
*自动生成于 2026-03-12 14:30 | [原始视频](url)*
```

辅助函数：`escape_yaml()`, `sanitize_filename()`, `format_yaml_tags()`
写入路径：`{vault_path}/0-收集箱/{sanitized_title}.md`

#### Step 8：pipeline.py

**`Pipeline` 类**：
- `__init__(config)` — 加载配置，初始化 SQLite
- `is_processed(video_id)` — 去重检查
- `process(url)` — 单视频完整流程：metadata → analyze → generate → 记录
- SQLite 表：`processed(video_id, title, url, processed_at, status)`

#### Step 9：main.py

```python
@click.group()
def cli(): pass

@cli.command()
@click.argument("url")
def process(url):
    """处理单个 YouTube 视频"""
    pipeline = Pipeline(load_config())
    asyncio.run(pipeline.process(url))
```

#### Step 10：端到端验证

```bash
# 1. 完成 NotebookLM 登录
uv run notebooklm login

# 2. 处理一个真实视频
uv run python main.py process "https://www.youtube.com/watch?v=<test-video>"

# 3. 检查生成的笔记
cat ~/obsidian/0-收集箱/<generated-note>.md

# 4. 在 Obsidian 中打开确认 frontmatter 解析正确
```

---

### Phase 2：丰富分析维度（Phase 1 验证通过后）

- 多 prompt 分析（concepts.txt → 概念卡片与关系、actions.txt → 可执行行动项）
- `parse_concepts_to_links()` 解析概念为 Obsidian 双向链接
- Mind map 生成 + JSON 导出到 `_附件/mindmaps/`
- Quiz 生成 + Markdown 导出到 `_附件/quizzes/`
- 标签标准化（kebab-case）
- frontmatter 新增字段：content_type, has_quiz, one_line_summary, rating

### Phase 3：批量处理 + 自动化（Phase 2 验证通过后）

- `python main.py batch urls.txt` — 批量处理（每视频间隔 5 秒）
- `python main.py channel <url> --last 5` — 频道最新视频
- `python main.py playlist <url>` — 播放列表
- `python main.py stats` — 处理统计
- Notebook 清理策略（处理完删除 or 按周/月合并）
- Dataview Dashboard 模板：`MOC/YouTube学习看板.md`、`MOC/频道索引.md`

### Phase 4：持续优化（后续迭代）

- MOC 自动更新
- 概念笔记自动创建
- Audio overview 生成（通勤复习）
- 跨视频主题关联
- 定时监听订阅频道

---

## 注意事项

1. **notebooklm-py 使用非官方 API**：Google 可能随时更改接口，保持 `uv add --upgrade notebooklm-py` 更新。认证 cookie 每几周过期，需重新 `uv run notebooklm login`。
2. **速率限制**：NotebookLM 有使用频率限制，批量处理时每视频间隔至少 5 秒。
3. **YouTube 视频限制**：需上传 72 小时以上、公开、有字幕（人工或自动）。
4. **Python 版本**：notebooklm-py 要求 >=3.10，项目用 uv 管理 Python 3.12 虚拟环境。
5. **成本**：NotebookLM 免费 + yt-dlp 免费，整条流水线零成本。

## 编码规范

- 异步优先：analyzer.py 使用 async/await
- 错误处理：所有外部调用（yt-dlp subprocess、NotebookLM API）加 try/except
- 路径处理：使用 pathlib.Path
- 日志：print 带 emoji 前缀（📥 提取、🧠 分析、📝 生成、✅ 完成、❌ 失败）
