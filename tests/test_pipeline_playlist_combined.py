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

    async def test_runs_multi_prompt_analysis_and_passes_results_to_note(self, base_config, tmp_vault):
        config = {
            **base_config,
            "notebooklm": {
                **base_config["notebooklm"],
                "analyze_type_specific": True,
                "analyze_concepts": True,
                "analyze_actions": True,
            },
        }
        pipeline = Pipeline(config)
        mock_client = _make_mock_client()
        mock_client.chat.ask = AsyncMock(side_effect=[
            MagicMock(answer="## 一句话总结\n综合分析\n\n## 内容类型\ntech_tutorial\n\n## 核心观点\n- 观点1\n\n## 详细笔记\n详细内容" + "x" * 100),
            MagicMock(answer="## 技术栈与环境要求\n- [[Claude Code]]\n- 环境要求：未明确提及\n- 前置技能：熟悉终端与 Git"),
            MagicMock(answer="## 关键概念\n### [[Agent Teams]]\n- **定义**：多个子智能体协同完成任务，并行处理复杂任务"),
            MagicMock(answer="## 行动项\n- [ ] 试用 [[Plan Mode]]\n  - 目的：先规划后执行\n  - 难度：简单"),
        ])

        loaded_prompts = []

        def fake_load_prompt(name):
            loaded_prompts.append(name)
            return f"prompt:{name}"

        with patch("src.pipeline.get_playlist_metadata", return_value=FAKE_PLAYLIST_META), \
             patch("src.pipeline.get_video_metadata", return_value=FAKE_VIDEO_META), \
             patch("src.pipeline.NotebookLMClient") as MockNLM, \
             patch("src.pipeline._load_prompt", side_effect=fake_load_prompt), \
             patch("src.pipeline.generate_playlist_note", return_value=tmp_vault / "playlist.md") as mock_generate:
            MockNLM.from_storage = AsyncMock(return_value=mock_client)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)

            await pipeline.process_playlist_combined(
                "https://www.youtube.com/playlist?list=PLtest123",
                last=None, force=False,
            )

        assert loaded_prompts == ["core_playlist", "type_tech_tutorial", "concepts", "actions"]
        assert mock_client.chat.ask.await_count == 4
        analysis = mock_generate.call_args.args[2]
        assert analysis["type_specific"].startswith("## 技术栈与环境要求")
        assert analysis["concepts"].startswith("## 关键概念")
        assert analysis["actions"].startswith("## 行动项")

    async def test_falls_back_to_requested_playlist_url_when_metadata_missing_it(self, base_config, tmp_vault):
        pipeline = Pipeline(base_config)
        mock_client = _make_mock_client()
        playlist_meta = {k: v for k, v in FAKE_PLAYLIST_META.items() if k != "url"}

        with patch("src.pipeline.get_playlist_metadata", return_value=playlist_meta), \
             patch("src.pipeline.get_video_metadata", return_value=FAKE_VIDEO_META), \
             patch("src.pipeline.NotebookLMClient") as MockNLM, \
             patch("src.pipeline._load_prompt", return_value="test prompt"), \
             patch("src.pipeline.generate_playlist_note", return_value=tmp_vault / "playlist.md") as mock_generate:
            MockNLM.from_storage = AsyncMock(return_value=mock_client)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)

            await pipeline.process_playlist_combined(
                "https://www.youtube.com/playlist?list=PLtest123",
                last=None, force=False,
            )

        playlist_arg = mock_generate.call_args.args[0]
        assert playlist_arg["url"] == "https://www.youtube.com/playlist?list=PLtest123"
