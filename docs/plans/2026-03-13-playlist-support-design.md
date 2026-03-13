# 播放列表批量分析设计

## 概述

支持批量处理 YouTube 播放列表，提供两种分析模式：逐个分析（individual）和合并分析（combined）。

## CLI 接口

```
python main.py playlist <url> [options]
```

**参数与选项：**
- `url` — YouTube 播放列表 URL
- `--mode individual|combined` — 分析模式，默认 `individual`
- `--last N` — 只处理最新 N 个视频
- `--delay N` — 视频间隔秒数，默认 5（仅 individual 模式）
- `--force` — 强制重新处理

**行为逻辑：**
- `individual`：逐个调用现有 `pipeline.process()`，每个视频间隔 `--delay` 秒
- `combined`：所有视频作为 source 加到同一个 Notebook，生成一篇综合笔记。超过 50 个视频时报错提示用 `--last`

## Extractor 扩展

新增 `get_playlist_metadata(url, last=None) -> dict`：

- 调用 `yt-dlp --dump-json --flat-playlist <url>`
- 如果指定 `last`，切片 `entries[-last:]`
- 返回结构：

```python
{
    "playlist_id": "PLxxxxx",
    "playlist_title": "播放列表标题",
    "channel": "频道名",
    "entries": [
        {"video_id": "xxx", "title": "视频标题", "url": "https://..."},
        ...
    ]
}
```

现有 `get_video_metadata()` 不需要改动。

## Pipeline 扩展

### 数据库

- 现有 `processed` 表不变
- 新增 `playlists` 表：

```sql
CREATE TABLE playlists (
    playlist_id TEXT PRIMARY KEY,
    title TEXT,
    url TEXT,
    video_count INTEGER,
    processed_at TEXT,
    status TEXT
)
```

### 去重逻辑

- `individual` 模式：按 `video_id` 去重（复用现有逻辑）
- `combined` 模式：按 `playlist_id` 去重，不记录视频级别

### 新增方法

**`async def process_playlist_individual(url, last, delay, force)`**
- 调用 `get_playlist_metadata(url, last)` 获取视频列表
- 遍历 entries，逐个调用 `self.process(entry_url, force)`
- 每个视频之间 `asyncio.sleep(delay)`
- 打印进度：`[3/12] 处理中: 视频标题`
- 最后打印汇总（成功/跳过/失败数量）

**`async def process_playlist_combined(url, last, force)`**
- 调用 `get_playlist_metadata(url, last)` 获取视频列表
- 检查 `len(entries) > 50`，报错提示用 `--last`
- 创建一个 Notebook，标题用播放列表标题
- 逐个将视频 URL 作为 source 添加到同一个 Notebook（路径 A 优先，路径 B 兜底）
- 调用 `chat.ask()` 用现有 `core.txt` prompt 做综合分析
- 调用 `generate_playlist_note()` 生成笔记
- 在 `playlists` 表记录 `playlist_id`

## Generator 扩展

新增 `generate_playlist_note(playlist_meta, entries_meta, analysis, config) -> Path`

生成笔记结构：

```markdown
---
type: youtube-playlist
title: "播放列表标题"
playlist_id: PLxxxxx
channel: "[[频道名]]"
url: https://youtube.com/playlist?list=PLxxxxx
video_count: 12
date_watched: 2026-03-13
tags:
  - playlist
---

# 播放列表标题

## 视频列表
| # | 标题 | 时长 |
|---|------|------|
| 1 | [[视频1标题]] | 10:23 |
| 2 | [[视频2标题]] | 15:47 |

{core analysis 综合分析内容}

---
*自动生成于 2026-03-13 14:30 | [原始播放列表](url)*
```

- 文件名：`sanitize_filename(playlist_title) + ".md"`
- 写入路径：`{vault_path}/0-收集箱/`
- `entries_meta` 用于视频列表表格中的 duration 信息

## 涉及文件变更

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `main.py` | 修改 | 新增 `playlist` 命令 |
| `src/extractor.py` | 修改 | 新增 `get_playlist_metadata()` |
| `src/pipeline.py` | 修改 | 新增 `playlists` 表、`process_playlist_individual()`、`process_playlist_combined()` |
| `src/generator.py` | 修改 | 新增 `generate_playlist_note()` |
| `config.yaml` | 修改 | 新增 `playlist.default_delay` 配置项 |
