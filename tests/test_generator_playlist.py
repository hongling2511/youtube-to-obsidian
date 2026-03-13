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
