"""Event handler for Discord events."""
import logging
from typing import Optional
import discord
from discord.ext import commands

from similubot.auth.authorization_manager import AuthorizationManager
from similubot.auth.unauthorized_handler import UnauthorizedAccessHandler
from similubot.downloaders.mega_downloader import MegaDownloader


class EventHandler:
    """
    Handles Discord events for SimiluBot.
    
    Manages bot lifecycle events and automatic feature detection
    with proper authorization checking.
    """

    def __init__(
        self,
        bot: commands.Bot,
        auth_manager: AuthorizationManager,
        unauthorized_handler: UnauthorizedAccessHandler,
        mega_downloader: Optional[MegaDownloader] = None,
        mega_processor_callback: Optional[callable] = None
    ):
        """
        Initialize the event handler.

        Args:
            bot: Discord bot instance
            auth_manager: Authorization manager
            unauthorized_handler: Unauthorized access handler
            mega_downloader: MEGA downloader instance (None if MEGA is disabled)
            mega_processor_callback: Callback for processing MEGA links
        """
        self.logger = logging.getLogger("similubot.events")
        self.bot = bot
        self.auth_manager = auth_manager
        self.unauthorized_handler = unauthorized_handler
        self.mega_downloader = mega_downloader
        self.mega_processor_callback = mega_processor_callback

        # Register event handlers
        self._register_events()

    def _register_events(self) -> None:
        """Register Discord event handlers."""
        @self.bot.event
        async def on_ready():
            await self._on_ready()

        @self.bot.event
        async def on_message(message):
            await self._on_message(message)

        @self.bot.event
        async def on_command_error(ctx, error):
            await self._on_command_error(ctx, error)

        self.logger.debug("Event handlers registered")

    async def _on_ready(self) -> None:
        """Handle bot ready event."""
        if self.bot.user is None:
            self.logger.error("Bot user is None in on_ready event")
            return

        self.logger.info(f"Bot is ready. Logged in as {self.bot.user.name} ({self.bot.user.id})")

        # Set bot status
        activity = discord.Activity(
            type=discord.ActivityType.listening,
            name=f"{self.bot.command_prefix}about"
        )
        await self.bot.change_presence(activity=activity)

        # Log authorization status
        if self.auth_manager.auth_enabled:
            stats = self.auth_manager.get_stats()
            self.logger.info(
                f"Authorization enabled: {stats['total_users']} users, "
                f"{stats['admin_users']} admins"
            )
        else:
            self.logger.info("Authorization disabled - all users have full access")

    async def _on_message(self, message: discord.Message) -> None:
        """
        Handle incoming messages.

        Args:
            message: Discord message
        """
        # Ignore messages from the bot itself
        if message.author == self.bot.user:
            return

        # Process commands first
        await self.bot.process_commands(message)

        # Check for MEGA links in messages (auto-detection)
        await self._handle_mega_auto_detection(message)

    async def _handle_mega_auto_detection(self, message: discord.Message) -> None:
        """
        Handle automatic MEGA link detection.

        Args:
            message: Discord message to check for MEGA links
        """
        # Skip if MEGA functionality is not available
        if not self.mega_downloader or not self.mega_downloader.is_available():
            return

        # Skip if message is empty or starts with command prefix
        if not message.content or message.content.startswith(self.bot.command_prefix):
            return

        # Extract MEGA links
        mega_links = self.mega_downloader.extract_mega_links(message.content)
        if not mega_links:
            return

        self.logger.info(f"Found MEGA links in message: {len(mega_links)}")

        # Check authorization for MEGA auto-detection
        if not self.auth_manager.is_authorized(
            str(message.author.id),
            feature_name="mega_auto_detection"
        ):
            await self.unauthorized_handler.handle_unauthorized_access(
                user=message.author,
                feature_name="mega_auto_detection",
                channel=message.channel
            )
            return

        # Process the first link if callback is available
        if self.mega_processor_callback:
            try:
                await self.mega_processor_callback(message, mega_links[0])
            except Exception as e:
                self.logger.error(f"Error processing MEGA link: {e}", exc_info=True)
                await message.reply(f"❌ Error processing MEGA link: {str(e)}")

    async def _on_command_error(self, ctx: commands.Context, error: Exception) -> None:
        """
        Handle command errors.

        Args:
            ctx: Command context
            error: Exception that occurred
        """
        # Handle specific error types
        if isinstance(error, commands.CommandNotFound):
            # Silently ignore unknown commands
            return
        
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.reply(f"❌ Missing required argument: `{error.param.name}`")
            await ctx.send_help(ctx.command)
            
        elif isinstance(error, commands.BadArgument):
            await ctx.reply(f"❌ Invalid argument: {str(error)}")
            await ctx.send_help(ctx.command)
            
        elif isinstance(error, commands.CommandOnCooldown):
            await ctx.reply(f"❌ Command is on cooldown. Try again in {error.retry_after:.1f} seconds.")
            
        elif isinstance(error, commands.NoPrivateMessage):
            await ctx.reply("❌ This command cannot be used in private messages.")
            
        elif isinstance(error, commands.DisabledCommand):
            await ctx.reply("❌ This command is currently disabled.")
            
        elif isinstance(error, commands.CheckFailure):
            # Authorization failures are handled by the command registry
            # This catches other check failures
            await ctx.reply("❌ You don't have permission to use this command.")
            
        else:
            # Log unexpected errors
            self.logger.error(
                f"Unexpected error in command {ctx.command}: {error}",
                exc_info=True
            )
            await ctx.reply(f"❌ An unexpected error occurred: {str(error)}")

    def set_mega_processor_callback(self, callback: callable) -> None:
        """
        Set the callback for processing MEGA links.

        Args:
            callback: Function to call when processing MEGA links
        """
        self.mega_processor_callback = callback
        self.logger.debug("MEGA processor callback set")

    async def send_startup_notification(self, channel_id: Optional[int] = None) -> None:
        """
        Send a startup notification to a specific channel.

        Args:
            channel_id: Discord channel ID to send notification to
        """
        if not channel_id:
            return

        try:
            channel = self.bot.get_channel(channel_id)
            if channel:
                embed = discord.Embed(
                    title="🤖 SimiluBot Online",
                    description="Bot has started successfully and is ready to process commands.",
                    color=0x2ecc71
                )
                
                if self.auth_manager.auth_enabled:
                    embed.add_field(
                        name="Authorization",
                        value="✅ Enabled",
                        inline=True
                    )
                else:
                    embed.add_field(
                        name="Authorization", 
                        value="❌ Disabled",
                        inline=True
                    )

                await channel.send(embed=embed)
                self.logger.info(f"Startup notification sent to channel {channel_id}")
                
        except Exception as e:
            self.logger.warning(f"Failed to send startup notification: {e}")

    async def send_shutdown_notification(self, channel_id: Optional[int] = None) -> None:
        """
        Send a shutdown notification to a specific channel.

        Args:
            channel_id: Discord channel ID to send notification to
        """
        if not channel_id:
            return

        try:
            channel = self.bot.get_channel(channel_id)
            if channel:
                embed = discord.Embed(
                    title="🤖 SimiluBot Offline",
                    description="Bot is shutting down.",
                    color=0xe74c3c
                )
                
                await channel.send(embed=embed)
                self.logger.info(f"Shutdown notification sent to channel {channel_id}")
                
        except Exception as e:
            self.logger.warning(f"Failed to send shutdown notification: {e}")

    def get_event_stats(self) -> dict:
        """
        Get event handling statistics.

        Returns:
            Dictionary with event statistics
        """
        return {
            "bot_ready": self.bot.is_ready(),
            "bot_user": str(self.bot.user) if self.bot.user else None,
            "guild_count": len(self.bot.guilds),
            "user_count": sum(guild.member_count or 0 for guild in self.bot.guilds),
            "authorization_enabled": self.auth_manager.auth_enabled
        }
