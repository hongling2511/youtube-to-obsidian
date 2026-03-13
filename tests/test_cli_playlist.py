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
