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
