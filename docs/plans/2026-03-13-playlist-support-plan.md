# Playlist Support Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add `playlist` CLI command supporting individual (per-video) and combined (multi-source NotebookLM) analysis modes for YouTube playlists.

**Architecture:** New `get_playlist_metadata()` in extractor uses `yt-dlp --flat-playlist`. Pipeline gets two new methods: `process_playlist_individual()` loops existing `process()` with delay, `process_playlist_combined()` adds all videos as sources to one Notebook. New `playlists` SQLite table for combined mode dedup. New `generate_playlist_note()` in generator for combined mode output.

**Tech Stack:** Python 3.12, yt-dlp, notebooklm-py, click, pytest

---

## Task 0: Set Up Test Infrastructure

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

**Step 1: Add pytest dependency**

```bash
cd /Users/hongling/youtube-to-obsidian && uv add --dev pytest pytest-asyncio
```

**Step 2: Create test infrastructure files**

`tests/__init__.py` — empty file.

`tests/conftest.py`:

```python
"""Shared test fixtures."""

import sqlite3
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def tmp_vault(tmp_path):
    """Create a temporary Obsidian vault with inbox folder."""
    inbox = tmp_path / "0-收集箱"
    inbox.mkdir()
    return tmp_path


@pytest.fixture
def base_config(tmp_vault):
    """Minimal config for testing."""
    return {
        "obsidian": {
            "vault_path": str(tmp_vault),
            "inbox_folder": "0-收集箱",
        },
        "youtube": {
            "preferred_languages": ["zh", "en"],
        },
        "notebooklm": {
            "cleanup_notebook": True,
            "generate_audio": False,
            "generate_mind_map": False,
            "generate_quiz": False,
            "generate_study_guide": False,
            "analyze_concepts": False,
            "analyze_actions": False,
            "analyze_type_specific": False,
        },
        "db_path": str(tmp_vault / "test.db"),
    }


SAMPLE_PLAYLIST_YTDLP_OUTPUT = [
    {
        "id": "vid001",
        "title": "Playlist Video 1",
        "url": "https://www.youtube.com/watch?v=vid001",
        "duration": 623,
        "uploader": "TestChannel",
    },
    {
        "id": "vid002",
        "title": "Playlist Video 2",
        "url": "https://www.youtube.com/watch?v=vid002",
        "duration": 1240,
        "uploader": "TestChannel",
    },
    {
        "id": "vid003",
        "title": "Playlist Video 3",
        "url": "https://www.youtube.com/watch?v=vid003",
        "duration": 845,
        "uploader": "TestChannel",
    },
]

SAMPLE_PLAYLIST_FLAT_OUTPUT = {
    "id": "PLtest123",
    "title": "Test Playlist Title",
    "channel": "TestChannel",
    "channel_url": "https://www.youtube.com/@TestChannel",
    "entries": SAMPLE_PLAYLIST_YTDLP_OUTPUT,
}
```

**Step 3: Verify pytest runs**

Run: `cd /Users/hongling/youtube-to-obsidian && uv run pytest tests/ -v --co`
Expected: "no tests ran" (collected 0 items), exit code 5

**Step 4: Commit**

```bash
git add tests/ pyproject.toml uv.lock
git commit -m "chore: add pytest infrastructure for playlist feature"
```

---

## Task 1: `get_playlist_metadata()` in Extractor

**Files:**
- Modify: `src/extractor.py` (append new function after `_parse_vtt_to_text`)
- Create: `tests/test_extractor_playlist.py`

**Step 1: Write the failing test**

Create `tests/test_extractor_playlist.py`:

```python
"""Tests for get_playlist_metadata()."""

import json
from unittest.mock import patch, MagicMock

import pytest

from src.extractor import get_playlist_metadata


def _make_flat_playlist_output(entries, playlist_title="Test Playlist", playlist_id="PLtest123", channel="TestChannel"):
    """Build multi-line JSON that yt-dlp --flat-playlist produces (one JSON object per line)."""
    lines = []
    for entry in entries:
        obj = {
            **entry,
            "playlist_title": playlist_title,
            "playlist_id": playlist_id,
            "playlist_channel": channel,
        }
        lines.append(json.dumps(obj))
    return "\n".join(lines)


class TestGetPlaylistMetadata:
    def test_basic_playlist(self):
        entries = [
            {"id": "vid001", "title": "Video 1", "url": "https://www.youtube.com/watch?v=vid001", "duration": 600},
            {"id": "vid002", "title": "Video 2", "url": "https://www.youtube.com/watch?v=vid002", "duration": 1200},
        ]
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = _make_flat_playlist_output(entries)

        with patch("src.extractor.subprocess.run", return_value=mock_result) as mock_run:
            result = get_playlist_metadata("https://www.youtube.com/playlist?list=PLtest123")

        assert result["playlist_id"] == "PLtest123"
        assert result["playlist_title"] == "Test Playlist"
        assert result["channel"] == "TestChannel"
        assert len(result["entries"]) == 2
        assert result["entries"][0]["video_id"] == "vid001"
        assert result["entries"][1]["video_id"] == "vid002"

        # Verify yt-dlp called with --flat-playlist
        call_args = mock_run.call_args[0][0]
        assert "--flat-playlist" in call_args
        assert "--dump-json" in call_args

    def test_last_param_slices_entries(self):
        entries = [
            {"id": f"vid{i:03d}", "title": f"Video {i}", "url": f"https://www.youtube.com/watch?v=vid{i:03d}", "duration": 600}
            for i in range(10)
        ]
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = _make_flat_playlist_output(entries)

        with patch("src.extractor.subprocess.run", return_value=mock_result):
            result = get_playlist_metadata("https://www.youtube.com/playlist?list=PLtest123", last=3)

        assert len(result["entries"]) == 3
        # Should be the LAST 3 entries
        assert result["entries"][0]["video_id"] == "vid007"
        assert result["entries"][2]["video_id"] == "vid009"

    def test_last_larger_than_entries_returns_all(self):
        entries = [
            {"id": "vid001", "title": "Video 1", "url": "https://www.youtube.com/watch?v=vid001", "duration": 600},
        ]
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = _make_flat_playlist_output(entries)

        with patch("src.extractor.subprocess.run", return_value=mock_result):
            result = get_playlist_metadata("https://www.youtube.com/playlist?list=PLtest123", last=50)

        assert len(result["entries"]) == 1

    def test_yt_dlp_failure_raises(self):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "ERROR: not a playlist"

        with patch("src.extractor.subprocess.run", return_value=mock_result):
            with pytest.raises(RuntimeError, match="yt-dlp 错误"):
                get_playlist_metadata("https://www.youtube.com/watch?v=bad")

    def test_empty_playlist_raises(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""

        with patch("src.extractor.subprocess.run", return_value=mock_result):
            with pytest.raises(RuntimeError, match="播放列表为空"):
                get_playlist_metadata("https://www.youtube.com/playlist?list=PLempty")
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/hongling/youtube-to-obsidian && uv run pytest tests/test_extractor_playlist.py -v`
Expected: FAIL with `ImportError: cannot import name 'get_playlist_metadata'`

**Step 3: Write minimal implementation**

Append to `src/extractor.py` (after `_parse_vtt_to_text` function, line 128):

```python
def get_playlist_metadata(url: str, last: int | None = None) -> dict:
    """调用 yt-dlp 提取播放列表元数据（不下载视频）

    Args:
        url: YouTube 播放列表 URL
        last: 只取最后 N 个视频，None 表示全部

    Returns:
        dict with keys: playlist_id, playlist_title, channel, entries
        每个 entry 包含: video_id, title, url, duration
    """
    print("📥 提取播放列表元数据...")
    try:
        result = subprocess.run(
            ["yt-dlp", "--dump-json", "--flat-playlist", url],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            raise RuntimeError(f"yt-dlp 错误: {result.stderr.strip()}")

        # yt-dlp --flat-playlist outputs one JSON object per line
        lines = [line for line in result.stdout.strip().splitlines() if line.strip()]
        if not lines:
            raise RuntimeError("播放列表为空或无法解析")

        entries = []
        playlist_id = ""
        playlist_title = ""
        channel = ""

        for line in lines:
            data = json.loads(line)
            if not playlist_id:
                playlist_id = data.get("playlist_id", "")
                playlist_title = data.get("playlist_title", "")
                channel = data.get("playlist_channel", data.get("channel", ""))

            video_id = data.get("id", "")
            video_url = data.get("url", "")
            # flat-playlist 的 url 可能是相对路径，需要补全
            if video_url and not video_url.startswith("http"):
                video_url = f"https://www.youtube.com/watch?v={video_id}"

            entries.append({
                "video_id": video_id,
                "title": data.get("title", ""),
                "url": video_url,
                "duration": data.get("duration", 0),
            })

        # --last 切片
        if last is not None and last > 0:
            entries = entries[-last:]

        print(f"✅ 播放列表: {playlist_title} ({len(entries)} 个视频)")
        return {
            "playlist_id": playlist_id,
            "playlist_title": playlist_title,
            "channel": channel,
            "entries": entries,
        }
    except subprocess.TimeoutExpired:
        raise RuntimeError("yt-dlp 超时（120秒）")
    except json.JSONDecodeError as e:
        raise RuntimeError(f"yt-dlp 输出解析失败: {e}")
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/hongling/youtube-to-obsidian && uv run pytest tests/test_extractor_playlist.py -v`
Expected: 5 passed

**Step 5: Commit**

```bash
git add src/extractor.py tests/test_extractor_playlist.py
git commit -m "feat: add get_playlist_metadata() for playlist URL extraction"
```

---

## Task 2: `playlists` Table + Dedup in Pipeline

**Files:**
- Modify: `src/pipeline.py` (add table creation in `_init_db`, add `is_playlist_processed` and `_record_playlist` methods)
- Create: `tests/test_pipeline_playlist_db.py`

**Step 1: Write the failing test**

Create `tests/test_pipeline_playlist_db.py`:

```python
"""Tests for playlist database operations in Pipeline."""

import pytest

from src.pipeline import Pipeline


class TestPlaylistDatabase:
    def test_playlists_table_created(self, base_config):
        pipeline = Pipeline(base_config)
        cursor = pipeline.db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='playlists'"
        )
        assert cursor.fetchone() is not None

    def test_is_playlist_processed_returns_false_for_new(self, base_config):
        pipeline = Pipeline(base_config)
        assert pipeline.is_playlist_processed("PLnew123") is False

    def test_record_and_check_playlist(self, base_config):
        pipeline = Pipeline(base_config)
        pipeline._record_playlist("PLtest123", "Test Playlist", "https://url", 5, "success")
        assert pipeline.is_playlist_processed("PLtest123") is True

    def test_failed_playlist_not_considered_processed(self, base_config):
        pipeline = Pipeline(base_config)
        pipeline._record_playlist("PLfail", "Failed", "https://url", 3, "failed")
        assert pipeline.is_playlist_processed("PLfail") is False
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/hongling/youtube-to-obsidian && uv run pytest tests/test_pipeline_playlist_db.py -v`
Expected: FAIL with `AttributeError: 'Pipeline' object has no attribute 'is_playlist_processed'`

**Step 3: Write minimal implementation**

In `src/pipeline.py`, modify `_init_db` method (line 22-31) to also create the playlists table:

```python
    def _init_db(self):
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS processed (
                video_id TEXT PRIMARY KEY,
                title TEXT,
                url TEXT,
                processed_at TEXT,
                status TEXT
            )
        """)
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS playlists (
                playlist_id TEXT PRIMARY KEY,
                title TEXT,
                url TEXT,
                video_count INTEGER,
                processed_at TEXT,
                status TEXT
            )
        """)
        self.db.commit()
```

Add two new methods after `_record` (after line 47):

```python
    def is_playlist_processed(self, playlist_id: str) -> bool:
        """检查播放列表是否已处理"""
        row = self.db.execute(
            "SELECT 1 FROM playlists WHERE playlist_id = ? AND status = 'success'",
            (playlist_id,),
        ).fetchone()
        return row is not None

    def _record_playlist(self, playlist_id: str, title: str, url: str, video_count: int, status: str):
        """记录播放列表处理结果"""
        self.db.execute(
            "INSERT OR REPLACE INTO playlists (playlist_id, title, url, video_count, processed_at, status) VALUES (?, ?, ?, ?, ?, ?)",
            (playlist_id, title, url, video_count, datetime.now().isoformat(), status),
        )
        self.db.commit()
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/hongling/youtube-to-obsidian && uv run pytest tests/test_pipeline_playlist_db.py -v`
Expected: 4 passed

**Step 5: Commit**

```bash
git add src/pipeline.py tests/test_pipeline_playlist_db.py
git commit -m "feat: add playlists table and dedup methods to Pipeline"
```

---

## Task 3: `generate_playlist_note()` in Generator

**Files:**
- Modify: `src/generator.py` (append new function)
- Create: `tests/test_generator_playlist.py`

**Step 1: Write the failing test**

Create `tests/test_generator_playlist.py`:

```python
"""Tests for generate_playlist_note()."""

from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from src.generator import generate_playlist_note


@pytest.fixture
def playlist_meta():
    return {
        "playlist_id": "PLtest123",
        "playlist_title": "Python 教程系列",
        "channel": "TestChannel",
        "url": "https://www.youtube.com/playlist?list=PLtest123",
    }


@pytest.fixture
def entries_meta():
    return [
        {"video_id": "vid001", "title": "第一课 基础语法", "duration_string": "10:23", "url": "https://www.youtube.com/watch?v=vid001"},
        {"video_id": "vid002", "title": "第二课 函数", "duration_string": "15:47", "url": "https://www.youtube.com/watch?v=vid002"},
    ]


@pytest.fixture
def analysis():
    return {
        "core": "## 一句话总结\nPython基础教程\n\n## 内容类型\ntech_tutorial\n\n## 核心观点\n- 观点1\n\n## 详细笔记\n详细内容",
    }


class TestGeneratePlaylistNote:
    def test_creates_file_in_inbox(self, tmp_vault, base_config, playlist_meta, entries_meta, analysis):
        result = generate_playlist_note(playlist_meta, entries_meta, analysis, base_config)
        assert result.exists()
        assert result.parent.name == "0-收集箱"
        assert result.suffix == ".md"

    def test_frontmatter_contains_playlist_fields(self, tmp_vault, base_config, playlist_meta, entries_meta, analysis):
        result = generate_playlist_note(playlist_meta, entries_meta, analysis, base_config)
        content = result.read_text(encoding="utf-8")
        assert "type: youtube-playlist" in content
        assert "playlist_id: PLtest123" in content
        assert "video_count: 2" in content
        assert "TestChannel" in content

    def test_body_contains_video_table(self, tmp_vault, base_config, playlist_meta, entries_meta, analysis):
        result = generate_playlist_note(playlist_meta, entries_meta, analysis, base_config)
        content = result.read_text(encoding="utf-8")
        assert "| # | 标题 | 时长 |" in content
        assert "第一课 基础语法" in content
        assert "10:23" in content
        assert "第二课 函数" in content

    def test_body_contains_analysis(self, tmp_vault, base_config, playlist_meta, entries_meta, analysis):
        result = generate_playlist_note(playlist_meta, entries_meta, analysis, base_config)
        content = result.read_text(encoding="utf-8")
        assert "Python基础教程" in content
        assert "观点1" in content

    def test_filename_from_playlist_title(self, tmp_vault, base_config, playlist_meta, entries_meta, analysis):
        result = generate_playlist_note(playlist_meta, entries_meta, analysis, base_config)
        assert "Python 教程系列" in result.stem

    def test_unsafe_chars_in_title_sanitized(self, tmp_vault, base_config, entries_meta, analysis):
        meta = {
            "playlist_id": "PLtest",
            "playlist_title": 'Test: "Unsafe" /Chars?',
            "channel": "Ch",
            "url": "https://example.com",
        }
        result = generate_playlist_note(meta, entries_meta, analysis, base_config)
        assert result.exists()
        # No unsafe chars in filename
        assert ":" not in result.name
        assert '"' not in result.name
        assert "?" not in result.name
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/hongling/youtube-to-obsidian && uv run pytest tests/test_generator_playlist.py -v`
Expected: FAIL with `ImportError: cannot import name 'generate_playlist_note'`

**Step 3: Write minimal implementation**

Append to `src/generator.py` (after `generate_obsidian_note`, after line 215):

```python
def generate_playlist_note(
    playlist_meta: dict, entries_meta: list[dict], analysis: dict, config: dict
) -> Path:
    """生成播放列表综合分析的 Obsidian 笔记并写入 Vault"""
    print("📝 生成播放列表笔记...")

    now = datetime.now()
    title = playlist_meta.get("playlist_title", "Untitled Playlist")
    vault_path = Path(config["obsidian"]["vault_path"])
    inbox = config["obsidian"].get("inbox_folder", "0-收集箱")
    output_dir = vault_path / inbox
    output_dir.mkdir(parents=True, exist_ok=True)

    # Frontmatter
    frontmatter_lines = [
        "---",
        "type: youtube-playlist",
        f"title: {escape_yaml(title)}",
        f"playlist_id: {playlist_meta.get('playlist_id', '')}",
        f'channel: "[[{playlist_meta.get("channel") or "Unknown"}]]"',
        f"url: {playlist_meta.get('url', '')}",
        f"video_count: {len(entries_meta)}",
        f"date_watched: {now.strftime('%Y-%m-%d')}",
        "tags:\n  - playlist",
        "---",
    ]
    frontmatter = "\n".join(frontmatter_lines)

    # Video table
    table_lines = [
        "## 视频列表",
        "| # | 标题 | 时长 |",
        "|---|------|------|",
    ]
    for i, entry in enumerate(entries_meta, 1):
        entry_title = entry.get("title", "Unknown")
        duration = entry.get("duration_string", "")
        table_lines.append(f"| {i} | {entry_title} | {duration} |")

    # Body
    core_answer = analysis.get("core", "")
    sections = [
        f"# {title}",
        "",
        "\n".join(table_lines),
        "",
        core_answer,
        "",
        "---",
        f"*自动生成于 {now.strftime('%Y-%m-%d %H:%M')} | [原始播放列表]({playlist_meta.get('url', '')})*",
    ]

    content = frontmatter + "\n\n" + "\n".join(sections) + "\n"

    filename = sanitize_filename(title) + ".md"
    filepath = output_dir / filename
    filepath.write_text(content, encoding="utf-8")

    print(f"✅ 播放列表笔记已写入: {filepath}")
    return filepath
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/hongling/youtube-to-obsidian && uv run pytest tests/test_generator_playlist.py -v`
Expected: 6 passed

**Step 5: Commit**

```bash
git add src/generator.py tests/test_generator_playlist.py
git commit -m "feat: add generate_playlist_note() for combined playlist output"
```

---

## Task 4: `process_playlist_individual()` in Pipeline

**Files:**
- Modify: `src/pipeline.py` (add new method and import)
- Create: `tests/test_pipeline_playlist_individual.py`

**Step 1: Write the failing test**

Create `tests/test_pipeline_playlist_individual.py`:

```python
"""Tests for process_playlist_individual()."""

import asyncio
from unittest.mock import patch, AsyncMock, MagicMock

import pytest

from src.pipeline import Pipeline


FAKE_PLAYLIST_META = {
    "playlist_id": "PLtest123",
    "playlist_title": "Test Playlist",
    "channel": "TestChannel",
    "entries": [
        {"video_id": "vid001", "title": "Video 1", "url": "https://www.youtube.com/watch?v=vid001", "duration": 600},
        {"video_id": "vid002", "title": "Video 2", "url": "https://www.youtube.com/watch?v=vid002", "duration": 1200},
        {"video_id": "vid003", "title": "Video 3", "url": "https://www.youtube.com/watch?v=vid003", "duration": 845},
    ],
}


@pytest.mark.asyncio
class TestProcessPlaylistIndividual:
    async def test_calls_process_for_each_entry(self, base_config):
        pipeline = Pipeline(base_config)

        with patch("src.pipeline.get_playlist_metadata", return_value=FAKE_PLAYLIST_META), \
             patch.object(pipeline, "process", new_callable=AsyncMock) as mock_process, \
             patch("asyncio.sleep", new_callable=AsyncMock):
            await pipeline.process_playlist_individual(
                "https://www.youtube.com/playlist?list=PLtest123",
                last=None, delay=0, force=False,
            )

        assert mock_process.call_count == 3
        mock_process.assert_any_call("https://www.youtube.com/watch?v=vid001", force=False)
        mock_process.assert_any_call("https://www.youtube.com/watch?v=vid002", force=False)
        mock_process.assert_any_call("https://www.youtube.com/watch?v=vid003", force=False)

    async def test_respects_delay_between_videos(self, base_config):
        pipeline = Pipeline(base_config)

        with patch("src.pipeline.get_playlist_metadata", return_value=FAKE_PLAYLIST_META), \
             patch.object(pipeline, "process", new_callable=AsyncMock), \
             patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await pipeline.process_playlist_individual(
                "https://www.youtube.com/playlist?list=PLtest123",
                last=None, delay=5, force=False,
            )

        # Sleep called between videos (not after the last one)
        assert mock_sleep.call_count == 2
        mock_sleep.assert_called_with(5)

    async def test_passes_last_to_get_playlist_metadata(self, base_config):
        pipeline = Pipeline(base_config)

        with patch("src.pipeline.get_playlist_metadata", return_value=FAKE_PLAYLIST_META) as mock_get, \
             patch.object(pipeline, "process", new_callable=AsyncMock), \
             patch("asyncio.sleep", new_callable=AsyncMock):
            await pipeline.process_playlist_individual(
                "https://www.youtube.com/playlist?list=PLtest123",
                last=2, delay=0, force=False,
            )

        mock_get.assert_called_once_with("https://www.youtube.com/playlist?list=PLtest123", last=2)

    async def test_continues_on_single_video_failure(self, base_config):
        pipeline = Pipeline(base_config)

        call_count = 0
        async def mock_process(url, force=False):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError("Video 2 failed")

        with patch("src.pipeline.get_playlist_metadata", return_value=FAKE_PLAYLIST_META), \
             patch.object(pipeline, "process", side_effect=mock_process), \
             patch("asyncio.sleep", new_callable=AsyncMock):
            await pipeline.process_playlist_individual(
                "https://www.youtube.com/playlist?list=PLtest123",
                last=None, delay=0, force=False,
            )

        # Should still attempt all 3 videos
        assert call_count == 3
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/hongling/youtube-to-obsidian && uv run pytest tests/test_pipeline_playlist_individual.py -v`
Expected: FAIL with `AttributeError: 'Pipeline' object has no attribute 'process_playlist_individual'`

**Step 3: Write minimal implementation**

Add import at top of `src/pipeline.py` (line 8, after existing imports):

```python
from src.extractor import get_video_metadata, get_playlist_metadata
```

And remove the existing `get_video_metadata` only import on line 9. The full import block becomes:

```python
from src.analyzer import analyze_video
from src.extractor import get_video_metadata, get_playlist_metadata
from src.generator import generate_obsidian_note
```

Add new method in `Pipeline` class, after `_record_playlist` method:

```python
    async def process_playlist_individual(
        self, url: str, last: int | None, delay: int, force: bool
    ):
        """逐个处理播放列表中的视频"""
        playlist = get_playlist_metadata(url, last=last)
        entries = playlist["entries"]
        total = len(entries)

        print(f"📋 播放列表: {playlist['playlist_title']} ({total} 个视频，逐个分析模式)")

        success = 0
        skipped = 0
        failed = 0

        for i, entry in enumerate(entries, 1):
            print(f"\n[{i}/{total}] 处理中: {entry['title']}")
            try:
                await self.process(entry["url"], force=force)
                success += 1
            except Exception as e:
                print(f"❌ [{i}/{total}] 失败: {e}")
                failed += 1

            # 非最后一个视频时等待
            if i < total and delay > 0:
                await asyncio.sleep(delay)

        print(f"\n📊 播放列表处理完成: ✅ {success} 成功 / ⏭️ {skipped} 跳过 / ❌ {failed} 失败")
```

Also add `import asyncio` at the top of `src/pipeline.py` (line 2, after the docstring):

```python
import asyncio
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/hongling/youtube-to-obsidian && uv run pytest tests/test_pipeline_playlist_individual.py -v`
Expected: 4 passed

**Step 5: Commit**

```bash
git add src/pipeline.py tests/test_pipeline_playlist_individual.py
git commit -m "feat: add process_playlist_individual() for per-video playlist processing"
```

---

## Task 5: `process_playlist_combined()` in Pipeline

**Files:**
- Modify: `src/pipeline.py` (add new method, add imports)
- Modify: `src/analyzer.py` (extract reusable `_add_source` and `_chat_analysis` — already public-friendly)
- Create: `tests/test_pipeline_playlist_combined.py`

**Step 1: Write the failing test**

Create `tests/test_pipeline_playlist_combined.py`:

```python
"""Tests for process_playlist_combined()."""

import asyncio
from unittest.mock import patch, AsyncMock, MagicMock, PropertyMock

import pytest

from src.pipeline import Pipeline


FAKE_PLAYLIST_META = {
    "playlist_id": "PLtest123",
    "playlist_title": "Test Playlist",
    "channel": "TestChannel",
    "entries": [
        {"video_id": "vid001", "title": "Video 1", "url": "https://www.youtube.com/watch?v=vid001", "duration": 600},
        {"video_id": "vid002", "title": "Video 2", "url": "https://www.youtube.com/watch?v=vid002", "duration": 1200},
    ],
}

FAKE_VIDEO_META = {
    "video_id": "vid001",
    "title": "Video 1",
    "channel": "TestChannel",
    "channel_url": "",
    "upload_date": "20260301",
    "duration": 600,
    "duration_string": "10:00",
    "description": "",
    "tags": [],
    "categories": [],
    "language": "",
    "chapters": [],
    "thumbnail": "",
    "view_count": 0,
    "url": "https://www.youtube.com/watch?v=vid001",
}


def _make_mock_client():
    """Create a mock NotebookLMClient with async context manager support."""
    client = AsyncMock()
    # notebooks.create returns an object with .id
    nb = MagicMock()
    nb.id = "nb_test_123"
    client.notebooks.create = AsyncMock(return_value=nb)
    client.notebooks.delete = AsyncMock()
    # sources.add_url is async
    client.sources.add_url = AsyncMock()
    # chat.ask returns object with .answer
    chat_result = MagicMock()
    chat_result.answer = "## 一句话总结\n综合分析\n\n## 内容类型\ntech_tutorial\n\n## 核心观点\n- 观点1\n\n## 详细笔记\n详细内容很长" + "x" * 100
    client.chat.ask = AsyncMock(return_value=chat_result)
    return client


@pytest.mark.asyncio
class TestProcessPlaylistCombined:
    async def test_rejects_over_50_videos(self, base_config):
        big_playlist = {
            **FAKE_PLAYLIST_META,
            "entries": [
                {"video_id": f"vid{i:03d}", "title": f"V{i}", "url": f"https://www.youtube.com/watch?v=vid{i:03d}", "duration": 600}
                for i in range(51)
            ],
        }

        pipeline = Pipeline(base_config)
        with patch("src.pipeline.get_playlist_metadata", return_value=big_playlist):
            with pytest.raises(ValueError, match="--last"):
                await pipeline.process_playlist_combined(
                    "https://www.youtube.com/playlist?list=PLtest123",
                    last=None, force=False,
                )

    async def test_adds_all_videos_as_sources(self, base_config, tmp_vault):
        pipeline = Pipeline(base_config)
        mock_client = _make_mock_client()

        with patch("src.pipeline.get_playlist_metadata", return_value=FAKE_PLAYLIST_META), \
             patch("src.pipeline.get_video_metadata", return_value=FAKE_VIDEO_META), \
             patch("src.pipeline.NotebookLMClient") as MockNLM, \
             patch("src.pipeline._load_prompt", return_value="test prompt"):
            MockNLM.from_storage = AsyncMock(return_value=mock_client)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)

            await pipeline.process_playlist_combined(
                "https://www.youtube.com/playlist?list=PLtest123",
                last=None, force=False,
            )

        # Should add 2 sources (one per video)
        assert mock_client.sources.add_url.call_count == 2

    async def test_records_playlist_in_db(self, base_config, tmp_vault):
        pipeline = Pipeline(base_config)
        mock_client = _make_mock_client()

        with patch("src.pipeline.get_playlist_metadata", return_value=FAKE_PLAYLIST_META), \
             patch("src.pipeline.get_video_metadata", return_value=FAKE_VIDEO_META), \
             patch("src.pipeline.NotebookLMClient") as MockNLM, \
             patch("src.pipeline._load_prompt", return_value="test prompt"):
            MockNLM.from_storage = AsyncMock(return_value=mock_client)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)

            await pipeline.process_playlist_combined(
                "https://www.youtube.com/playlist?list=PLtest123",
                last=None, force=False,
            )

        assert pipeline.is_playlist_processed("PLtest123")

    async def test_skips_already_processed_playlist(self, base_config):
        pipeline = Pipeline(base_config)
        pipeline._record_playlist("PLtest123", "Test", "https://url", 2, "success")

        with patch("src.pipeline.get_playlist_metadata", return_value=FAKE_PLAYLIST_META):
            # Should return without processing
            await pipeline.process_playlist_combined(
                "https://www.youtube.com/playlist?list=PLtest123",
                last=None, force=False,
            )

        # No NotebookLM calls should have been made — if it tried, it would
        # fail because we didn't mock the client
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/hongling/youtube-to-obsidian && uv run pytest tests/test_pipeline_playlist_combined.py -v`
Expected: FAIL with `AttributeError: 'Pipeline' object has no attribute 'process_playlist_combined'`

**Step 3: Write minimal implementation**

Add imports at top of `src/pipeline.py`:

```python
from notebooklm import NotebookLMClient

from src.analyzer import _add_source, _chat_analysis, _load_prompt
from src.extractor import get_video_metadata, get_playlist_metadata, extract_transcript
from src.generator import generate_obsidian_note, generate_playlist_note
```

(Replace the existing import lines for `analyzer`, `extractor`, and `generator`.)

Add new method in `Pipeline` class, after `process_playlist_individual`:

```python
    async def process_playlist_combined(
        self, url: str, last: int | None, force: bool
    ):
        """合并分析播放列表：所有视频作为 source 加到一个 Notebook"""
        playlist = get_playlist_metadata(url, last=last)
        entries = playlist["entries"]
        playlist_id = playlist["playlist_id"]

        # 去重检查
        if not force and self.is_playlist_processed(playlist_id):
            print(f"⏭️ 播放列表已处理过: {playlist['playlist_title']}（使用 --force 强制重新处理）")
            return

        # 数量限制
        if len(entries) > 50:
            raise ValueError(
                f"播放列表包含 {len(entries)} 个视频，超过 NotebookLM 50 source 上限。"
                f"请使用 --last 50 或更小的数字限制处理数量。"
            )

        print(f"📋 播放列表: {playlist['playlist_title']} ({len(entries)} 个视频，合并分析模式)")

        async with await NotebookLMClient.from_storage() as client:
            # 1. 创建 Notebook
            nb_title = f"PL: {playlist['playlist_title'][:80]}"
            nb = await client.notebooks.create(nb_title)
            print(f"🧠 Notebook 已创建: {nb_title}")

            # 2. 逐个添加视频为 source
            added = 0
            for i, entry in enumerate(entries, 1):
                print(f"  [{i}/{len(entries)}] 添加源: {entry['title']}")
                try:
                    await client.sources.add_url(nb.id, entry["url"])
                    added += 1
                except Exception as e:
                    # 路径 B 兜底
                    print(f"  ⚠️ URL 添加失败，尝试字幕: {e}")
                    try:
                        transcript = extract_transcript(entry["url"])
                        if transcript:
                            await client.sources.add_text(nb.id, transcript, title=entry["title"])
                            added += 1
                        else:
                            print(f"  ❌ 跳过: {entry['title']}（无法获取内容）")
                    except Exception as e2:
                        print(f"  ❌ 跳过: {entry['title']}（{e2}）")

            if added == 0:
                await client.notebooks.delete(nb.id)
                raise ValueError("无法添加任何视频源到 Notebook")

            print(f"✅ 已添加 {added}/{len(entries)} 个视频源")

            # 3. 核心分析
            print("🧠 正在综合分析...")
            prompt = _load_prompt("core")
            result = await client.chat.ask(nb.id, prompt)
            core = result.answer

            # 4. 清理 Notebook
            if self.config.get("notebooklm", {}).get("cleanup_notebook", True):
                try:
                    await client.notebooks.delete(nb.id)
                    print("🧠 Notebook 已清理")
                except Exception:
                    pass

        # 5. 获取每个视频的详细元数据（用于笔记中的视频列表表格）
        entries_meta = []
        for entry in entries:
            try:
                meta = get_video_metadata(entry["url"])
                entries_meta.append(meta)
            except Exception:
                entries_meta.append({
                    "video_id": entry["video_id"],
                    "title": entry["title"],
                    "duration_string": "",
                    "url": entry["url"],
                })

        # 6. 生成笔记
        analysis = {"core": core}
        filepath = generate_playlist_note(playlist, entries_meta, analysis, self.config)

        # 7. 记录成功
        self._record_playlist(playlist_id, playlist["playlist_title"], url, len(entries), "success")
        print(f"✅ 完成: {playlist['playlist_title']} → {filepath}")
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/hongling/youtube-to-obsidian && uv run pytest tests/test_pipeline_playlist_combined.py -v`
Expected: 4 passed

**Step 5: Commit**

```bash
git add src/pipeline.py tests/test_pipeline_playlist_combined.py
git commit -m "feat: add process_playlist_combined() for multi-source NotebookLM analysis"
```

---

## Task 6: CLI `playlist` Command

**Files:**
- Modify: `main.py` (add new click command)
- Create: `tests/test_cli_playlist.py`

**Step 1: Write the failing test**

Create `tests/test_cli_playlist.py`:

```python
"""Tests for playlist CLI command."""

from unittest.mock import patch, AsyncMock, MagicMock

from click.testing import CliRunner

from main import cli


class TestPlaylistCommand:
    def test_playlist_command_exists(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["playlist", "--help"])
        assert result.exit_code == 0
        assert "--mode" in result.output
        assert "--last" in result.output
        assert "--delay" in result.output
        assert "--force" in result.output

    def test_mode_individual_calls_correct_method(self):
        runner = CliRunner()
        mock_pipeline = MagicMock()
        mock_pipeline.process_playlist_individual = AsyncMock()

        with patch("main.Pipeline", return_value=mock_pipeline), \
             patch("main.load_config", return_value={"db_path": ":memory:"}):
            result = runner.invoke(cli, [
                "playlist", "https://www.youtube.com/playlist?list=PLtest",
                "--mode", "individual", "--delay", "0",
            ])

        mock_pipeline.process_playlist_individual.assert_called_once()

    def test_mode_combined_calls_correct_method(self):
        runner = CliRunner()
        mock_pipeline = MagicMock()
        mock_pipeline.process_playlist_combined = AsyncMock()

        with patch("main.Pipeline", return_value=mock_pipeline), \
             patch("main.load_config", return_value={"db_path": ":memory:"}):
            result = runner.invoke(cli, [
                "playlist", "https://www.youtube.com/playlist?list=PLtest",
                "--mode", "combined",
            ])

        mock_pipeline.process_playlist_combined.assert_called_once()

    def test_default_mode_is_individual(self):
        runner = CliRunner()
        mock_pipeline = MagicMock()
        mock_pipeline.process_playlist_individual = AsyncMock()

        with patch("main.Pipeline", return_value=mock_pipeline), \
             patch("main.load_config", return_value={"db_path": ":memory:"}):
            result = runner.invoke(cli, [
                "playlist", "https://www.youtube.com/playlist?list=PLtest",
                "--delay", "0",
            ])

        mock_pipeline.process_playlist_individual.assert_called_once()
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/hongling/youtube-to-obsidian && uv run pytest tests/test_cli_playlist.py -v`
Expected: FAIL — "playlist" command not found

**Step 3: Write minimal implementation**

Add to `main.py`, after the `process` command (after line 33):

```python
@cli.command()
@click.argument("url")
@click.option("--mode", type=click.Choice(["individual", "combined"]), default="individual", help="分析模式")
@click.option("--last", type=int, default=None, help="只处理最新 N 个视频")
@click.option("--delay", type=int, default=5, help="视频间隔秒数（仅 individual 模式）")
@click.option("--force", is_flag=True, help="强制重新处理")
def playlist(url, mode, last, delay, force):
    """处理 YouTube 播放列表"""
    config = load_config()
    pipeline = Pipeline(config)
    if mode == "combined":
        asyncio.run(pipeline.process_playlist_combined(url, last=last, force=force))
    else:
        asyncio.run(pipeline.process_playlist_individual(url, last=last, delay=delay, force=force))
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/hongling/youtube-to-obsidian && uv run pytest tests/test_cli_playlist.py -v`
Expected: 4 passed

**Step 5: Commit**

```bash
git add main.py tests/test_cli_playlist.py
git commit -m "feat: add playlist CLI command with individual/combined modes"
```

---

## Task 7: Run Full Test Suite + Config Update

**Files:**
- Modify: `config.yaml` (add playlist section)

**Step 1: Run the full test suite**

Run: `cd /Users/hongling/youtube-to-obsidian && uv run pytest tests/ -v`
Expected: All tests pass (19 total across 5 test files)

**Step 2: Add playlist config**

Add to `config.yaml` after the `notebooklm` section:

```yaml
playlist:
  default_delay: 5           # individual 模式默认间隔秒数
```

**Step 3: Run full test suite again**

Run: `cd /Users/hongling/youtube-to-obsidian && uv run pytest tests/ -v`
Expected: All tests still pass

**Step 4: Commit**

```bash
git add config.yaml
git commit -m "chore: add playlist config section"
```
