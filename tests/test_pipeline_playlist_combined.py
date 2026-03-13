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
