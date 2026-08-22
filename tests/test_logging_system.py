"""
Test suite for the logging system functionality.

Tests the logger setup with configuration values and ensures proper
file and console logging behavior.
"""
import logging
import os
import tempfile
import unittest
from unittest.mock import patch

from similubot.utils.logger import setup_logger


class TestLoggingSystem(unittest.TestCase):
    """Test cases for the logging system."""

    def setUp(self):
        """Set up test fixtures."""
        # Clear any existing handlers
        logger = logging.getLogger("similubot")
        logger.handlers.clear()
        
    def tearDown(self):
        """Clean up after tests."""
        # Close and clear handlers after each test
        logger = logging.getLogger("similubot")
        for handler in logger.handlers:
            handler.close()
        logger.handlers.clear()

    def test_setup_logger_with_defaults(self):
        """Test logger setup with default parameters."""
        setup_logger()
        
        logger = logging.getLogger("similubot")
        
        # Check logger level
        self.assertEqual(logger.level, logging.INFO)
        
        # Check that console handler is added
        self.assertEqual(len(logger.handlers), 1)
        self.assertIsInstance(logger.handlers[0], logging.StreamHandler)
        
        # Check that propagation is disabled
        self.assertFalse(logger.propagate)

    def test_setup_logger_with_debug_level(self):
        """Test logger setup with DEBUG level."""
        setup_logger(log_level="DEBUG")
        
        logger = logging.getLogger("similubot")
        
        # Check logger level
        self.assertEqual(logger.level, logging.DEBUG)

    def test_setup_logger_with_file_logging(self):
        """Test logger setup with file logging."""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_file = os.path.join(temp_dir, "test.log")

            setup_logger(log_level="INFO", log_file=log_file)

            logger = logging.getLogger("similubot")

            # Check that both console and file handlers are added
            self.assertEqual(len(logger.handlers), 2)

            # Test logging to file
            logger.info("Test message")

            # Close handlers before checking file
            for handler in logger.handlers:
                handler.close()
            logger.handlers.clear()

            # Check that file was created and contains the message
            self.assertTrue(os.path.exists(log_file))
            with open(log_file, 'r', encoding='utf-8') as f:
                content = f.read()
                self.assertIn("Test message", content)

    def test_setup_logger_invalid_level(self):
        """Test logger setup with invalid log level."""
        with self.assertRaises(ValueError) as context:
            setup_logger(log_level="INVALID")
        
        self.assertIn("Invalid log level: INVALID", str(context.exception))

    def test_setup_logger_case_insensitive_level(self):
        """Test logger setup with case insensitive log level."""
        setup_logger(log_level="debug")
        
        logger = logging.getLogger("similubot")
        self.assertEqual(logger.level, logging.DEBUG)

    def test_setup_logger_creates_log_directory(self):
        """Test that logger creates log directory if it doesn't exist."""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_file = os.path.join(temp_dir, "subdir", "test.log")

            # Ensure subdirectory doesn't exist
            self.assertFalse(os.path.exists(os.path.dirname(log_file)))

            setup_logger(log_file=log_file)

            # Check that directory was created
            self.assertTrue(os.path.exists(os.path.dirname(log_file)))

            # Close handlers before cleanup
            logger = logging.getLogger("similubot")
            for handler in logger.handlers:
                handler.close()
            logger.handlers.clear()

    def test_setup_logger_handles_file_permission_error(self):
        """Test logger gracefully handles file permission errors."""
        # Try to write to a location that should fail (root directory on most systems)
        invalid_path = "/root/test.log" if os.name != 'nt' else "C:\\Windows\\System32\\test.log"
        
        # This should not raise an exception, but log a warning
        setup_logger(log_file=invalid_path)
        
        logger = logging.getLogger("similubot")
        
        # Should only have console handler
        self.assertEqual(len(logger.handlers), 1)
        self.assertIsInstance(logger.handlers[0], logging.StreamHandler)

    def test_multiple_setup_calls_clear_handlers(self):
        """Test that multiple setup calls don't create duplicate handlers."""
        # First setup
        setup_logger(log_level="INFO")
        logger = logging.getLogger("similubot")
        initial_handler_count = len(logger.handlers)
        
        # Second setup
        setup_logger(log_level="DEBUG")
        final_handler_count = len(logger.handlers)
        
        # Should have same number of handlers
        self.assertEqual(initial_handler_count, final_handler_count)
        
        # Level should be updated
        self.assertEqual(logger.level, logging.DEBUG)


if __name__ == '__main__':
    unittest.main()
