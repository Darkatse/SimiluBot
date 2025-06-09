"""Comprehensive tests for MEGA functionality."""
import unittest
import tempfile
import os
import sys
from unittest.mock import MagicMock, patch, AsyncMock
import pytest

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from similubot.downloaders.mega_downloader import MegaDownloader
from similubot.converters.audio_converter import AudioConverter
from similubot.commands.mega_commands import MegaCommands


class TestMegaDownloader(unittest.TestCase):
    """Test MEGA downloader functionality."""

    def setUp(self):
        """Set up test fixtures."""
        # Test with availability check disabled to avoid MegaCMD dependency
        self.downloader = MegaDownloader(check_availability=False)

    def test_downloader_initialization(self):
        """Test MEGA downloader initialization."""
        self.assertIsNotNone(self.downloader)

    def test_downloader_availability_disabled(self):
        """Test MEGA downloader with availability check disabled."""
        downloader = MegaDownloader(check_availability=False)
        self.assertFalse(downloader.is_available())

    @patch('similubot.downloaders.mega_downloader.subprocess.run')
    def test_downloader_availability_enabled_success(self, mock_run):
        """Test MEGA downloader with successful availability check."""
        # Mock successful MegaCMD check
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "MEGAcmd version 1.6.3"

        downloader = MegaDownloader(check_availability=True)
        self.assertTrue(downloader.is_available())

    @patch('similubot.downloaders.mega_downloader.subprocess.run')
    def test_downloader_availability_enabled_failure(self, mock_run):
        """Test MEGA downloader with failed availability check."""
        # Mock failed MegaCMD check
        mock_run.side_effect = FileNotFoundError("MegaCMD not found")

        downloader = MegaDownloader(check_availability=True)
        self.assertFalse(downloader.is_available())


class TestAudioConverter(unittest.TestCase):
    """Test audio conversion functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.converter = AudioConverter()

    def test_converter_initialization(self):
        """Test audio converter initialization."""
        self.assertIsNotNone(self.converter)


class TestMegaCommands(unittest.TestCase):
    """Test MEGA commands functionality."""

    def setUp(self):
        """Set up test fixtures."""
        # Create mock dependencies
        self.mock_config = MagicMock()
        self.mock_config.get_mega_upload_service.return_value = "catbox"
        self.mock_config.get_default_bitrate.return_value = 128

        self.mock_downloader = MagicMock()
        self.mock_downloader.is_available.return_value = True
        self.mock_converter = MagicMock()
        self.mock_catbox_uploader = MagicMock()
        self.mock_discord_uploader = MagicMock()

        self.mega_commands = MegaCommands(
            config=self.mock_config,
            downloader=self.mock_downloader,
            converter=self.mock_converter,
            catbox_uploader=self.mock_catbox_uploader,
            discord_uploader=self.mock_discord_uploader
        )

    def test_mega_commands_initialization(self):
        """Test MEGA commands initialization."""
        self.assertIsNotNone(self.mega_commands)

    def test_mega_commands_availability_with_downloader(self):
        """Test MEGA commands availability when downloader is available."""
        self.assertTrue(self.mega_commands.is_available())

    def test_mega_commands_availability_without_downloader(self):
        """Test MEGA commands availability when downloader is None."""
        mega_commands = MegaCommands(
            config=self.mock_config,
            downloader=None,
            converter=self.mock_converter,
            catbox_uploader=self.mock_catbox_uploader,
            discord_uploader=self.mock_discord_uploader
        )
        self.assertFalse(mega_commands.is_available())

    def test_mega_commands_availability_with_unavailable_downloader(self):
        """Test MEGA commands availability when downloader is not available."""
        self.mock_downloader.is_available.return_value = False
        self.assertFalse(self.mega_commands.is_available())

    def test_mega_commands_registration_when_available(self):
        """Test MEGA commands registration when available."""
        # Create mock registry
        mock_registry = MagicMock()

        # Register commands
        self.mega_commands.register_commands(mock_registry)

        # Verify registration was called
        mock_registry.register_command.assert_called_once()
        call_args = mock_registry.register_command.call_args[1]
        self.assertEqual(call_args['name'], 'mega')
        self.assertIsNotNone(call_args['usage_examples'])
        self.assertIsNotNone(call_args['help_text'])

    def test_mega_commands_registration_when_unavailable(self):
        """Test MEGA commands registration when unavailable."""
        # Create unavailable MEGA commands
        mega_commands = MegaCommands(
            config=self.mock_config,
            downloader=None,
            converter=self.mock_converter,
            catbox_uploader=self.mock_catbox_uploader,
            discord_uploader=self.mock_discord_uploader
        )

        # Create mock registry
        mock_registry = MagicMock()

        # Register commands
        mega_commands.register_commands(mock_registry)

        # Verify registration was NOT called
        mock_registry.register_command.assert_not_called()


if __name__ == "__main__":
    unittest.main()
