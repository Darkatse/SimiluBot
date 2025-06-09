"""Refactored main Discord bot implementation for SimiluBot."""
import logging
import os
from typing import Optional
import discord
from discord.ext import commands

# Core modules
from similubot.core.command_registry import CommandRegistry
from similubot.core.event_handler import EventHandler

# Command modules
from similubot.commands.mega_commands import MegaCommands
from similubot.commands.novelai_commands import NovelAICommands
from similubot.commands.auth_commands import AuthCommands
from similubot.commands.general_commands import GeneralCommands
from similubot.commands.ai_commands import AICommands
from similubot.commands.music_commands import MusicCommands

# Existing modules
from similubot.downloaders.mega_downloader import MegaDownloader
from similubot.converters.audio_converter import AudioConverter
from similubot.uploaders.catbox_uploader import CatboxUploader
from similubot.uploaders.discord_uploader import DiscordUploader
from similubot.generators.image_generator import ImageGenerator
from similubot.music.music_player import MusicPlayer
from similubot.utils.config_manager import ConfigManager
from similubot.auth.authorization_manager import AuthorizationManager
from similubot.auth.unauthorized_handler import UnauthorizedAccessHandler


class SimiluBot:
    """
    Main Discord bot implementation for SimiluBot.

    Refactored modular architecture with separation of concerns:
    - Command registry for centralized command management
    - Event handler for Discord events
    - Separate command modules for different features
    - Clean initialization and lifecycle management
    """

    def __init__(self, config: ConfigManager):
        """
        Initialize the Discord bot.

        Args:
            config: Configuration manager
        """
        self.logger = logging.getLogger("similubot.bot")
        self.config = config

        # Set up Discord bot
        intents = discord.Intents.default()
        intents.message_content = True

        self.bot = commands.Bot(
            command_prefix=self.config.get('discord.command_prefix', '!'),
            intents=intents,
            help_command=None  # We'll use our custom help command
        )

        # Initialize core components
        self._init_core_modules()

        # Initialize command modules
        self._init_command_modules()

        # Register commands and events
        self._register_commands()
        self._setup_event_handlers()

        self.logger.info("SimiluBot initialized successfully")

    def _init_core_modules(self) -> None:
        """Initialize core bot modules."""
        # Create temp directory if it doesn't exist
        temp_dir = self.config.get_download_temp_dir()
        if not os.path.exists(temp_dir):
            os.makedirs(temp_dir)
            self.logger.debug(f"Created temporary directory: {temp_dir}")

        # Initialize MEGA downloader (if enabled)
        if self.config.is_mega_enabled():
            try:
                self.downloader = MegaDownloader(temp_dir=temp_dir, check_availability=True)
                if self.downloader.is_available():
                    self.logger.info("MEGA downloader initialized successfully")
                else:
                    self.logger.warning("MEGA downloader initialization failed - MegaCMD not available")
                    self.downloader = None
            except Exception as e:
                self.logger.error(f"Failed to initialize MEGA downloader: {e}")
                self.downloader = None
        else:
            self.logger.info("MEGA functionality disabled in configuration")
            self.downloader = None

        # Initialize converter
        self.converter = AudioConverter(
            default_bitrate=self.config.get_default_bitrate(),
            supported_formats=self.config.get_supported_formats(),
            temp_dir=temp_dir
        )

        # Initialize uploaders
        self.catbox_uploader = CatboxUploader(
            user_hash=self.config.get_catbox_user_hash()
        )
        self.discord_uploader = DiscordUploader()

        # Initialize image generator (if NovelAI is configured)
        try:
            self.image_generator = ImageGenerator(
                api_key=self.config.get_novelai_api_key(),
                base_url=self.config.get_novelai_base_url(),
                timeout=self.config.get_novelai_timeout(),
                temp_dir=temp_dir
            )
            self.logger.info("NovelAI image generator initialized successfully")
        except ValueError as e:
            self.logger.warning(f"NovelAI not configured: {e}")
            self.image_generator = None

        # Initialize authorization system
        self.auth_manager = AuthorizationManager(
            config_path=self.config.get_auth_config_path(),
            auth_enabled=self.config.is_auth_enabled()
        )

        # Initialize unauthorized access handler
        self.unauthorized_handler = UnauthorizedAccessHandler(
            auth_manager=self.auth_manager,
            bot=self.bot
        )

        # Initialize music player
        self.music_player = MusicPlayer(
            bot=self.bot,
            temp_dir=temp_dir
        )

        # Initialize command registry
        self.command_registry = CommandRegistry(
            bot=self.bot,
            auth_manager=self.auth_manager,
            unauthorized_handler=self.unauthorized_handler
        )

        self.logger.debug("Core modules initialized")

    def _init_command_modules(self) -> None:
        """Initialize command modules."""
        # Initialize MEGA commands
        self.mega_commands = MegaCommands(
            config=self.config,
            downloader=self.downloader,
            converter=self.converter,
            catbox_uploader=self.catbox_uploader,
            discord_uploader=self.discord_uploader
        )

        # Initialize NovelAI commands
        self.novelai_commands = NovelAICommands(
            config=self.config,
            image_generator=self.image_generator,
            catbox_uploader=self.catbox_uploader,
            discord_uploader=self.discord_uploader
        )

        # Initialize authorization commands
        self.auth_commands = AuthCommands(
            auth_manager=self.auth_manager
        )

        # Initialize general commands
        self.general_commands = GeneralCommands(
            config=self.config,
            image_generator=self.image_generator
        )

        # Initialize AI commands
        self.ai_commands = AICommands(
            config=self.config
        )

        # Initialize music commands
        self.music_commands = MusicCommands(
            config=self.config,
            music_player=self.music_player
        )

        self.logger.debug("Command modules initialized")

    def _register_commands(self) -> None:
        """Register all commands with the command registry."""
        # Register MEGA commands (if available)
        if self.mega_commands.is_available():
            self.mega_commands.register_commands(self.command_registry)
        else:
            self.logger.info("MEGA commands not registered (not available)")

        # Register NovelAI commands (if available)
        if self.novelai_commands.is_available():
            self.novelai_commands.register_commands(self.command_registry)
        else:
            self.logger.info("NovelAI commands not registered (not configured)")

        # Register authorization commands (if enabled)
        if self.auth_commands.is_available():
            self.auth_commands.register_commands(self.command_registry)
        else:
            self.logger.info("Authorization commands not registered (auth disabled)")

        # Register general commands
        self.general_commands.register_commands(self.command_registry)

        # Register AI commands (if available)
        if self.ai_commands.is_available():
            self.ai_commands.register_commands(self.command_registry)
        else:
            self.logger.info("AI commands not registered (not configured)")

        # Register music commands (if available)
        if self.music_commands.is_available():
            self.music_commands.register_commands(self.command_registry)
        else:
            self.logger.info("Music commands not registered (disabled)")

        self.logger.info("All commands registered successfully")

    def _setup_event_handlers(self) -> None:
        """Set up Discord event handlers."""
        # Initialize event handler
        mega_processor_callback = None
        if self.mega_commands.is_available():
            mega_processor_callback = self.mega_commands.process_mega_link

        self.event_handler = EventHandler(
            bot=self.bot,
            auth_manager=self.auth_manager,
            unauthorized_handler=self.unauthorized_handler,
            mega_downloader=self.downloader,
            mega_processor_callback=mega_processor_callback
        )

        self.logger.debug("Event handlers set up")

    async def start(self, token: str) -> None:
        """
        Start the Discord bot.

        Args:
            token: Discord bot token
        """
        try:
            self.logger.info("Starting SimiluBot...")
            await self.bot.start(token)
        except Exception as e:
            self.logger.error(f"Failed to start bot: {e}", exc_info=True)
            raise

    async def close(self) -> None:
        """Close the Discord bot and clean up resources."""
        try:
            self.logger.info("Shutting down SimiluBot...")

            # Shutdown AI commands if available
            if hasattr(self, 'ai_commands') and self.ai_commands.is_available():
                await self.ai_commands.shutdown()

            # Cleanup music commands if available
            if hasattr(self, 'music_commands'):
                await self.music_commands.cleanup()

            # Cleanup music player if available
            if hasattr(self, 'music_player'):
                await self.music_player.cleanup_all()

            # Send shutdown notification if configured
            # await self.event_handler.send_shutdown_notification(channel_id)

            await self.bot.close()
            self.logger.info("SimiluBot shut down successfully")
        except Exception as e:
            self.logger.error(f"Error during shutdown: {e}", exc_info=True)

    def run(self, token: str) -> None:
        """
        Run the Discord bot (blocking).

        Args:
            token: Discord bot token
        """
        try:
            self.bot.run(token)
        except KeyboardInterrupt:
            self.logger.info("Bot stopped by user")
        except Exception as e:
            self.logger.error(f"Bot crashed: {e}", exc_info=True)
            raise

    def get_stats(self) -> dict:
        """
        Get bot statistics.

        Returns:
            Dictionary with bot statistics
        """
        stats = {
            "bot_ready": self.bot.is_ready(),
            "guild_count": len(self.bot.guilds),
            "user_count": sum(guild.member_count or 0 for guild in self.bot.guilds),
            "command_count": len(self.command_registry.get_registered_commands()),
            "authorization_enabled": self.auth_manager.auth_enabled,
            "novelai_available": self.image_generator is not None,
            "ai_available": self.ai_commands.is_available()
        }

        if self.auth_manager.auth_enabled:
            stats.update(self.auth_manager.get_stats())

        # Add AI conversation statistics if available
        if self.ai_commands.is_available() and self.ai_commands.conversation_memory:
            ai_stats = self.ai_commands.conversation_memory.get_conversation_stats()
            stats.update({
                "ai_active_conversations": ai_stats["active_conversations"],
                "ai_total_messages": ai_stats["total_messages"]
            })

        return stats

    def get_registered_commands(self) -> dict:
        """
        Get all registered commands.

        Returns:
            Dictionary of registered commands
        """
        return self.command_registry.get_registered_commands()

    def is_ready(self) -> bool:
        """
        Check if the bot is ready.

        Returns:
            True if bot is ready, False otherwise
        """
        return self.bot.is_ready()

    @property
    def user(self) -> Optional[discord.ClientUser]:
        """Get the bot user."""
        return self.bot.user

    @property
    def latency(self) -> float:
        """Get the bot latency."""
        return self.bot.latency

    @property
    def guilds(self) -> list:
        """Get the bot guilds."""
        return self.bot.guilds
