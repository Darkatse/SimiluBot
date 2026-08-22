"""SimiluBot composition root and Discord lifecycle."""

from __future__ import annotations

import logging
import os

import discord
from discord.ext import commands

from similubot.auth.authorization_manager import AuthorizationManager
from similubot.auth.unauthorized_handler import UnauthorizedAccessHandler
from similubot.commands.ai_commands import AICommands
from similubot.commands.auth_commands import AuthCommands
from similubot.commands.general_commands import GeneralCommands
from similubot.commands.mega_commands import MegaCommands
from similubot.commands.music_commands import MusicCommands
from similubot.commands.nai import NaiCog
from similubot.converters.audio_converter import AudioConverter
from similubot.core.command_registry import CommandRegistry
from similubot.core.event_handler import EventHandler
from similubot.downloaders.mega_downloader import MegaDownloader
from similubot.music.music_player import MusicPlayer
from similubot.novelai.client import NovelAIClient
from similubot.novelai.service import NaiService
from similubot.novelai.store import NaiStore
from similubot.uploaders.catbox_uploader import CatboxUploader
from similubot.uploaders.discord_uploader import DiscordUploader
from similubot.utils.config_manager import ConfigManager


class SimiluBot(commands.Bot):
    """The bot itself; feature modules receive this single Discord client."""

    def __init__(self, config: ConfigManager):
        self.logger = logging.getLogger("similubot.bot")
        self.config = config
        intents = discord.Intents.default()
        intents.message_content = config.get("discord.message_content_intent", True)
        super().__init__(
            command_prefix=config.get("discord.command_prefix", "!"),
            intents=intents,
            help_command=None,
        )
        self._init_core_modules()
        self._init_command_modules()
        self._register_prefix_commands()
        self._setup_event_handlers()

    def _init_core_modules(self) -> None:
        temp_dir = self.config.get_download_temp_dir()
        os.makedirs(temp_dir, exist_ok=True)

        self.downloader = None
        if self.config.is_mega_enabled():
            downloader = MegaDownloader(temp_dir=temp_dir, check_availability=True)
            if downloader.is_available():
                self.downloader = downloader
            else:
                self.logger.warning(
                    "MegaCMD is unavailable; MEGA commands are disabled"
                )

        self.converter = AudioConverter(
            default_bitrate=self.config.get_default_bitrate(),
            supported_formats=self.config.get_supported_formats(),
            temp_dir=temp_dir,
        )
        self.catbox_uploader = CatboxUploader(
            user_hash=self.config.get_catbox_user_hash()
        )
        self.discord_uploader = DiscordUploader()

        self.auth_manager = AuthorizationManager(
            config_path=self.config.get_auth_config_path(),
            auth_enabled=self.config.is_auth_enabled(),
            admin_ids=self.config.get_admin_ids(),
        )
        self.unauthorized_handler = UnauthorizedAccessHandler(self.auth_manager, self)
        self.music_player = MusicPlayer(self, temp_dir=temp_dir, config=self.config)
        self.command_registry = CommandRegistry(
            self, self.auth_manager, self.unauthorized_handler
        )

        try:
            client = NovelAIClient(
                self.config.get_novelai_api_key,
                self.config.get_novelai_base_url(),
                self.config.get_novelai_timeout(),
            )
        except ValueError:
            self.nai_service: NaiService | None = None
            self.logger.warning(
                "NOVELAI_KEY is not configured; /nai commands are disabled"
            )
        else:
            self.nai_service = NaiService(
                client,
                NaiStore(self.config.get_novelai_state_path()),
                self.config.get_novelai_default_model(),
            )

    def _init_command_modules(self) -> None:
        self.mega_commands = MegaCommands(
            self.config,
            self.downloader,
            self.converter,
            self.catbox_uploader,
            self.discord_uploader,
        )
        self.auth_commands = AuthCommands(self.auth_manager)
        self.general_commands = GeneralCommands(
            self.config, self.nai_service is not None
        )
        self.ai_commands = AICommands(self.config)
        self.music_commands = MusicCommands(self.config, self.music_player)

    def _register_prefix_commands(self) -> None:
        for module in (
            self.mega_commands,
            self.auth_commands,
            self.ai_commands,
            self.music_commands,
        ):
            if module.is_available():
                module.register_commands(self.command_registry)
        self.general_commands.register_commands(self.command_registry)

    def _setup_event_handlers(self) -> None:
        mega_callback = (
            self.mega_commands.process_mega_link
            if self.mega_commands.is_available()
            else None
        )
        self.event_handler = EventHandler(
            self,
            self.auth_manager,
            self.unauthorized_handler,
            self.downloader,
            mega_callback,
        )

    async def setup_hook(self) -> None:
        guild_id = self.config.get_command_guild_id()
        guild = discord.Object(id=guild_id) if guild_id else None
        if self.nai_service is not None:
            await self.nai_service.initialize()
            await self.add_cog(NaiCog(self.nai_service, self.auth_manager), guild=guild)
        synced = await self.tree.sync(guild=guild)
        scope = f"guild {guild_id}" if guild_id else "global"
        self.logger.info("Synced %d application commands (%s)", len(synced), scope)

    async def close(self) -> None:
        self.logger.info("Shutting down SimiluBot")
        try:
            if self.ai_commands.is_available():
                await self.ai_commands.shutdown()
            await self.music_commands.cleanup()
            await self.music_player.cleanup_all()
            if self.nai_service is not None:
                await self.nai_service.close()
        finally:
            await super().close()

    def get_stats(self) -> dict[str, object]:
        stats: dict[str, object] = {
            "bot_ready": self.is_ready(),
            "guild_count": len(self.guilds),
            "user_count": sum(guild.member_count or 0 for guild in self.guilds),
            "command_count": len(self.command_registry.get_registered_commands()),
            "authorization_enabled": self.auth_manager.auth_enabled,
            "novelai_available": self.nai_service is not None,
            "ai_available": self.ai_commands.is_available(),
        }
        if self.auth_manager.auth_enabled:
            stats.update(self.auth_manager.get_stats())
        if self.ai_commands.is_available() and self.ai_commands.conversation_memory:
            conversation = self.ai_commands.conversation_memory.get_conversation_stats()
            stats.update(
                ai_active_conversations=conversation["active_conversations"],
                ai_total_messages=conversation["total_messages"],
            )
        return stats

    def get_registered_commands(self) -> dict:
        return self.command_registry.get_registered_commands()
