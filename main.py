#!/usr/bin/env python3
"""
SimiluBot - Discord bot for downloading MEGA links and converting media to AAC format.

Main entry point for the SimiluBot application. Handles configuration loading,
bot initialization, and graceful startup/shutdown with proper error handling.
"""
import logging

from similubot.bot import SimiluBot
from similubot.utils.config_manager import ConfigManager
from similubot.utils.logger import setup_logger

def main() -> int:
    """
    Main entry point for the SimiluBot application.

    Handles the complete lifecycle of the bot including:
    - Logging setup
    - Configuration loading and validation
    - Bot initialization
    - Graceful startup and shutdown

    Returns:
        int: Exit code (0 for success, 1 for error)
    """
    # Set up logging
    setup_logger()
    logger = logging.getLogger("similubot")

    logger.info("=" * 50)
    logger.info("SimiluBot Starting Up")
    logger.info("=" * 50)

    try:
        # Load configuration
        logger.info("Loading configuration...")
        config = ConfigManager()
        logger.info("✅ Configuration loaded successfully")

        # Get Discord token from configuration
        logger.info("Retrieving Discord bot token...")
        try:
            discord_token = config.get_discord_token()
            logger.info("✅ Discord token retrieved from configuration")
        except ValueError as e:
            logger.error(f"❌ Discord token configuration error: {e}")
            logger.error("Please check your config/config.yaml file and ensure the Discord token is set")
            logger.error("Example: discord.token: 'YOUR_ACTUAL_BOT_TOKEN_HERE'")
            return 1

        # Initialize the bot
        logger.info("Initializing SimiluBot...")
        bot = SimiluBot(config)
        logger.info("✅ SimiluBot initialized successfully")

        # Log bot configuration summary
        _log_bot_configuration(logger, config, bot)

        # Run the bot with the token
        logger.info("🚀 Starting SimiluBot...")
        logger.info("Press Ctrl+C to stop the bot")
        bot.run(discord_token)

    except KeyboardInterrupt:
        logger.info("🛑 Bot stopped by user (Ctrl+C)")
        logger.info("Goodbye!")
        return 0
    except FileNotFoundError as e:
        logger.error(f"❌ Configuration file error: {e}")
        logger.error("Please ensure config/config.yaml exists and is properly configured")
        return 1
    except Exception as e:
        logger.error(f"❌ Unexpected error starting SimiluBot: {e}", exc_info=True)
        logger.error("Please check the logs above for more details")
        return 1

    return 0


def _log_bot_configuration(logger: logging.Logger, config: ConfigManager, bot: SimiluBot) -> None:
    """
    Log bot configuration summary for debugging and monitoring.

    Args:
        logger: Logger instance
        config: Configuration manager
        bot: SimiluBot instance
    """
    logger.info("📋 Bot Configuration Summary:")
    logger.info(f"   Command Prefix: {config.get('discord.command_prefix', '!')}")
    logger.info(f"   Authorization: {'✅ Enabled' if config.is_auth_enabled() else '❌ Disabled'}")
    logger.info(f"   MEGA Functionality: {'✅ Enabled' if config.is_mega_enabled() and bot.mega_commands.is_available() else '❌ Disabled'}")
    logger.info(f"   Default Bitrate: {config.get_default_bitrate()} kbps")
    logger.info(f"   MEGA Upload Service: {config.get_mega_upload_service()}")
    logger.info(f"   NovelAI Available: {'✅ Yes' if bot.image_generator else '❌ No'}")

    if bot.image_generator:
        logger.info(f"   NovelAI Upload Service: {config.get_novelai_upload_service()}")

    if config.is_auth_enabled():
        admin_count = len(config.get_admin_ids())
        logger.info(f"   Admin Users: {admin_count}")

    logger.info("=" * 50)

if __name__ == "__main__":
    exit(main())
