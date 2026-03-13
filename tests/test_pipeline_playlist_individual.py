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
