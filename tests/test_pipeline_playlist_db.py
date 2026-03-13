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
