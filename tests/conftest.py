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
