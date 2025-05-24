"""Tests for progress tracking functionality."""
import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from similubot.progress.discord_updater import DiscordProgressUpdater
from similubot.progress.base import ProgressInfo, ProgressStatus


class TestProgressTracking(unittest.TestCase):
    """Test cases for progress tracking functionality."""

    def setUp(self):
        """Set up test fixtures."""
        # Create mock Discord message
        self.mock_message = MagicMock()
        self.mock_message.edit = AsyncMock()

    @pytest.mark.asyncio
    async def test_discord_progress_updater_callback_with_progress_info(self):
        """Test Discord progress updater callback with ProgressInfo object."""
        # Create Discord progress updater
        updater = DiscordProgressUpdater(self.mock_message, update_interval=0.1)
        callback = updater.create_callback()

        # Create progress info
        progress = ProgressInfo(
            operation="download",
            status=ProgressStatus.IN_PROGRESS,
            percentage=50.0,
            message="Downloading file... (50%)"
        )

        # Call the callback
        await callback(progress)

        # Give it a moment to process
        await asyncio.sleep(0.2)

        # Verify the message was edited
        self.mock_message.edit.assert_called()

    @pytest.mark.asyncio
    async def test_discord_progress_updater_callback_with_individual_params(self):
        """Test Discord progress updater callback with individual parameters."""
        # Create Discord progress updater
        updater = DiscordProgressUpdater(self.mock_message, update_interval=0.1)
        callback = updater.create_callback()

        # Call the callback with individual parameters
        await callback("optimization", "🔧 Optimizing file size...", 0.75)

        # Give it a moment to process
        await asyncio.sleep(0.2)

        # Verify the message was edited
        self.mock_message.edit.assert_called()

    @pytest.mark.asyncio
    async def test_discord_progress_updater_percentage_conversion(self):
        """Test that percentage values are correctly converted."""
        # Create Discord progress updater
        updater = DiscordProgressUpdater(self.mock_message, update_interval=0.1)
        callback = updater.create_callback()

        # Test with 0-1 range (should be converted to 0-100)
        await callback("test", "Testing...", 0.5)
        await asyncio.sleep(0.1)

        # Test with 0-100 range (should remain as-is)
        await callback("test", "Testing...", 50.0)
        await asyncio.sleep(0.1)

        # Verify the message was edited multiple times
        assert self.mock_message.edit.call_count >= 2

    @pytest.mark.asyncio
    async def test_discord_progress_updater_invalid_args(self):
        """Test Discord progress updater with invalid arguments."""
        # Create Discord progress updater
        updater = DiscordProgressUpdater(self.mock_message, update_interval=0.1)
        callback = updater.create_callback()

        # Call with invalid arguments (should not crash)
        await callback()  # No arguments
        await callback("single_arg")  # Single argument that's not ProgressInfo

        # Give it a moment to process
        await asyncio.sleep(0.1)

        # Should not have called edit due to invalid arguments
        self.mock_message.edit.assert_not_called()

    @pytest.mark.asyncio
    async def test_mega_download_progress_integration(self):
        """Test MEGA download progress integration."""
        from similubot.bot import SimiluBot
        from similubot.utils.config_manager import ConfigManager

        # Create mock config
        mock_config = MagicMock(spec=ConfigManager)
        mock_config.get_download_temp_dir.return_value = "/tmp"
        mock_config.get_default_bitrate.return_value = 320
        mock_config.get_supported_formats.return_value = ["mp3", "flac", "wav"]
        mock_config.get_catbox_user_hash.return_value = "test_hash"
        mock_config.get_mega_upload_service.return_value = "catbox"
        mock_config.get_novelai_api_key.side_effect = ValueError("Not configured")
        mock_config.get.return_value = "!"

        # Create bot instance with mocked dependencies
        with patch('similubot.bot.os.makedirs'), \
             patch('similubot.bot.os.path.exists', return_value=True), \
             patch('similubot.bot.MegaDownloader') as mock_downloader_class, \
             patch('similubot.bot.AudioConverter') as mock_converter_class, \
             patch('similubot.bot.CatboxUploader') as mock_catbox_class, \
             patch('similubot.bot.DiscordUploader') as mock_discord_class:

            # Set up mock instances
            mock_downloader = MagicMock()
            mock_converter = MagicMock()
            mock_catbox_uploader = MagicMock()
            mock_discord_uploader = MagicMock()

            mock_downloader_class.return_value = mock_downloader
            mock_converter_class.return_value = mock_converter
            mock_catbox_class.return_value = mock_catbox_uploader
            mock_discord_class.return_value = mock_discord_uploader

            bot = SimiluBot(mock_config)

            # Mock Discord message
            mock_message = MagicMock()
            mock_message.reply = AsyncMock()

            # Mock successful operations
            mock_downloader.download_with_progress.return_value = (True, "/tmp/test.mp3", None)
            mock_converter.convert_to_aac_with_progress.return_value = (True, "/tmp/test.aac", None)
            mock_catbox_uploader.upload_with_progress.return_value = (True, "https://files.catbox.moe/test.aac", None)

            # Mock file size check (small file, no optimization needed)
            with patch('os.path.getsize', return_value=50 * 1024 * 1024):  # 50MB
                # Test the MEGA processing workflow
                await bot._process_mega_link(mock_message, "https://mega.nz/file/test", 320)

            # Verify all operations were called
            mock_downloader.download_with_progress.assert_called_once()
            mock_converter.convert_to_aac_with_progress.assert_called_once()
            mock_catbox_uploader.upload_with_progress.assert_called_once()

            # Verify progress callbacks were passed
            download_call = mock_downloader.download_with_progress.call_args
            assert download_call is not None
            assert len(download_call[0]) >= 2  # URL and callback

            convert_call = mock_converter.convert_to_aac_with_progress.call_args
            assert convert_call is not None
            assert len(convert_call[0]) >= 4  # input, bitrate, output, callback

            upload_call = mock_catbox_uploader.upload_with_progress.call_args
            assert upload_call is not None
            assert len(upload_call[0]) >= 2  # file and callback

    @pytest.mark.asyncio
    async def test_progress_callback_async_handling(self):
        """Test that async progress callbacks are handled correctly."""
        from similubot.progress.mega_tracker import MegaProgressTracker

        # Create progress tracker
        tracker = MegaProgressTracker()

        # Create async callback
        callback_called = False
        callback_progress = None

        async def async_callback(progress):
            nonlocal callback_called, callback_progress
            callback_called = True
            callback_progress = progress

        # Add async callback
        tracker.add_callback(async_callback)

        # Start tracking and update progress
        tracker.start()
        tracker.update(percentage=50.0, message="Test progress")

        # Give async callback time to execute
        await asyncio.sleep(0.1)

        # Verify callback was called
        assert callback_called
        assert callback_progress is not None
        assert callback_progress.percentage == 50.0
        assert "Test progress" in callback_progress.message

    @pytest.mark.asyncio
    async def test_progress_callback_mixed_sync_async(self):
        """Test that both sync and async callbacks work together."""
        from similubot.progress.mega_tracker import MegaProgressTracker

        # Create progress tracker
        tracker = MegaProgressTracker()

        # Create sync and async callbacks
        sync_called = False
        async_called = False

        def sync_callback(progress):
            nonlocal sync_called
            sync_called = True

        async def async_callback(progress):
            nonlocal async_called
            async_called = True

        # Add both callbacks
        tracker.add_callback(sync_callback)
        tracker.add_callback(async_callback)

        # Update progress
        tracker.update(percentage=75.0, message="Mixed callback test")

        # Give async callback time to execute
        await asyncio.sleep(0.1)

        # Verify both callbacks were called
        assert sync_called
        assert async_called


if __name__ == "__main__":
    pytest.main([__file__])
