"""General bot commands."""
import logging
import time
from typing import Optional
import discord
from discord.ext import commands

from similubot.core.command_registry import CommandRegistry
from similubot.utils.config_manager import ConfigManager


class GeneralCommands:
    """
    General bot command handlers.

    Handles informational commands and bot status information.
    """

    def __init__(self, config: ConfigManager, novelai_available: bool = False):
        """
        Initialize general commands.

        Args:
            config: Configuration manager
            novelai_available: Whether slash-based NovelAI commands are configured
        """
        self.logger = logging.getLogger("similubot.commands.general")
        self.config = config
        self.novelai_available = novelai_available

    def register_commands(self, registry: CommandRegistry) -> None:
        """
        Register general commands with the command registry.

        Args:
            registry: Command registry instance
        """
        registry.register_command(
            name="about",
            callback=self.about_command,
            description="Show information about the bot",
            required_permission="about"
        )

        registry.register_command(
            name="help",
            callback=self.help_command,
            description="Show help information",
            required_permission="help"
        )

        registry.register_command(
            name="status",
            callback=self.status_command,
            description="Show bot status information",
            required_permission="status"
        )

        registry.register_command(
            name="ping",
            callback=self.ping_command,
            description="Check bot latency and connection quality",
            required_permission="ping"
        )

        self.logger.debug("General commands registered")

    async def about_command(self, ctx: commands.Context) -> None:
        """
        Show information about the bot.

        Args:
            ctx: Discord command context
        """
        embed = discord.Embed(
            title="About SimiluBot",
            description="A bot for downloading MEGA links and converting media to AAC format.",
            color=discord.Color.blue()
        )

        # MEGA command information
        embed.add_field(
            name=f"{ctx.bot.command_prefix}mega <url> [bitrate]",
            value="Download a file from MEGA and convert it to AAC format.",
            inline=False
        )

        # Add NovelAI command if available
        if self.novelai_available:
            nai_description = "Generate with NovelAI using your saved model, UC, guidance, and size defaults."
            nai_description += "\nUse `/nai defaults`, `/nai artist`, and `/nai quota` to manage them."
            embed.add_field(
                name="/nai draw prompt:<prompt>",
                value=nai_description,
                inline=False
            )

        # Add AI command if available
        if self.config.is_ai_configured():
            ai_description = "Interact with AI for conversations and assistance."
            ai_description += "\nSupports conversation memory and specialized modes."
            ai_description += f"\nAdd `mode:danbooru` for Danbooru tag generation."
            embed.add_field(
                name=f"{ctx.bot.command_prefix}ai <prompt> [mode:danbooru]",
                value=ai_description,
                inline=False
            )

        # Automatic MEGA link detection
        embed.add_field(
            name="Automatic MEGA Link Detection",
            value="The bot will automatically detect and process MEGA links in messages.",
            inline=False
        )

        # Supported formats
        embed.add_field(
            name="Supported Formats",
            value=", ".join(self.config.get_supported_formats()),
            inline=False
        )

        # Default bitrate
        embed.add_field(
            name="Default Bitrate",
            value=f"{self.config.get_default_bitrate()} kbps",
            inline=False
        )

        # Bot information
        embed.add_field(
            name="Bot Information",
            value=f"Guilds: {len(ctx.bot.guilds)}\nUsers: {sum(guild.member_count or 0 for guild in ctx.bot.guilds)}",
            inline=True
        )

        # Version and links
        embed.add_field(
            name="Links",
            value="[GitHub](https://github.com/Darkatse/similubot) • [Support](https://www.youtube.com/watch?v=dQw4w9WgXcQ)",
            inline=True
        )

        embed.set_footer(text="SimiluBot • Powered by Python & discord.py")
        embed.timestamp = discord.utils.utcnow()

        await ctx.send(embed=embed)

    async def help_command(self, ctx: commands.Context, command_name: Optional[str] = None) -> None:
        """
        Show help information.

        Args:
            ctx: Discord command context
            command_name: Specific command to get help for (optional)
        """
        if command_name:
            # Show help for specific command
            command = ctx.bot.get_command(command_name)
            if command:
                embed = discord.Embed(
                    title=f"Help: {ctx.bot.command_prefix}{command.name}",
                    description=command.help or "No description available.",
                    color=0x3498db
                )

                if command.usage:
                    embed.add_field(
                        name="Usage",
                        value=f"`{ctx.bot.command_prefix}{command.name} {command.usage}`",
                        inline=False
                    )

                if command.aliases:
                    embed.add_field(
                        name="Aliases",
                        value=", ".join([f"`{alias}`" for alias in command.aliases]),
                        inline=False
                    )

                await ctx.send(embed=embed)
            else:
                await ctx.reply(f"❌ Command `{command_name}` not found.")
        else:
            # Show general help
            embed = discord.Embed(
                title="SimiluBot Help",
                description="Available commands and features",
                color=0x3498db
            )

            # Core commands
            core_commands = []
            core_commands.append(f"`{ctx.bot.command_prefix}mega <url> [bitrate]` - Download and convert MEGA files")

            if self.novelai_available:
                core_commands.append("`/nai draw` - Generate a NovelAI image")

            if self.config.is_ai_configured():
                core_commands.append(f"`{ctx.bot.command_prefix}ai <prompt>` - AI conversation and assistance")

            core_commands.append(f"`{ctx.bot.command_prefix}about` - Bot information")
            core_commands.append(f"`{ctx.bot.command_prefix}status` - Bot status")
            core_commands.append(f"`{ctx.bot.command_prefix}ping` - Check latency and connection quality")

            embed.add_field(
                name="📋 Core Commands",
                value="\n".join(core_commands),
                inline=False
            )

            # Features
            features = [
                "🔗 Automatic MEGA link detection",
                "🎵 Audio format conversion",
                "📤 Multiple upload services",
                "🔐 Permission system"
            ]

            embed.add_field(
                name="✨ Features",
                value="\n".join(features),
                inline=False
            )

            # Get help for specific command
            embed.add_field(
                name="💡 Need More Help?",
                value=f"Use `{ctx.bot.command_prefix}help <command>` for detailed command information.",
                inline=False
            )

            embed.set_footer(text="SimiluBot Help System")
            await ctx.send(embed=embed)

    async def status_command(self, ctx: commands.Context) -> None:
        """
        Show bot status information.

        Args:
            ctx: Discord command context
        """
        embed = discord.Embed(
            title="🤖 Bot Status",
            color=0x2ecc71
        )

        # Bot basic info
        embed.add_field(
            name="Bot Information",
            value=f"**Name:** {ctx.bot.user.name}\n**ID:** {ctx.bot.user.id}\n**Latency:** {round(ctx.bot.latency * 1000)}ms",
            inline=True
        )

        # Server stats
        embed.add_field(
            name="Server Statistics",
            value=f"**Guilds:** {len(ctx.bot.guilds)}\n**Users:** {sum(guild.member_count or 0 for guild in ctx.bot.guilds)}\n**Channels:** {len(list(ctx.bot.get_all_channels()))}",
            inline=True
        )

        # Feature availability
        features_status = []
        features_status.append(f"🔗 MEGA Downloads: ✅ Available")

        if self.novelai_available:
            features_status.append(f"🎨 NovelAI Generation: ✅ Available")
        else:
            features_status.append(f"🎨 NovelAI Generation: ❌ Not Configured")

        embed.add_field(
            name="Feature Status",
            value="\n".join(features_status),
            inline=False
        )

        # Configuration info
        config_info = []
        config_info.append(f"**Default Bitrate:** {self.config.get_default_bitrate()} kbps")
        config_info.append(f"**MEGA Upload Service:** {self.config.get_mega_upload_service()}")

        if self.novelai_available:
            config_info.append(f"**NovelAI Model:** {self.config.get_novelai_default_model()}")

        embed.add_field(
            name="Configuration",
            value="\n".join(config_info),
            inline=False
        )

        # System status
        embed.add_field(
            name="System Status",
            value="🟢 All systems operational",
            inline=False
        )

        embed.set_thumbnail(url=ctx.bot.user.avatar.url if ctx.bot.user.avatar else None)
        embed.timestamp = discord.utils.utcnow()
        embed.set_footer(text="SimiluBot Status")

        await ctx.send(embed=embed)

    async def ping_command(self, ctx: commands.Context) -> None:
        """
        Check bot latency and connection quality.

        Measures both Discord WebSocket latency and API response time,
        displaying results with visual quality indicators.

        Args:
            ctx: Discord command context
        """
        self.logger.debug(f"Ping command invoked by {ctx.author} in {ctx.guild}")

        try:
            # Measure API latency by timing a simple Discord API call
            api_start = time.perf_counter()

            # Use a lightweight API call to measure response time
            # We'll fetch the bot's own user info as it's cached and fast
            await ctx.bot.fetch_user(ctx.bot.user.id)

            api_end = time.perf_counter()
            api_latency_ms = round((api_end - api_start) * 1000, 2)

            # Get WebSocket latency (already in seconds, convert to ms)
            websocket_latency_ms = round(ctx.bot.latency * 1000, 2)

            self.logger.debug(f"Measured latencies - API: {api_latency_ms}ms, WebSocket: {websocket_latency_ms}ms")

            # Determine connection quality and visual indicators
            api_quality = self._get_latency_quality(api_latency_ms)
            ws_quality = self._get_latency_quality(websocket_latency_ms)

            # Overall quality is the worse of the two
            overall_quality = min(api_quality["level"], ws_quality["level"])
            overall_indicator = self._get_quality_indicator(overall_quality)

            # Create embed with results
            embed = discord.Embed(
                title=f"🏓 Pong! {overall_indicator['emoji']}",
                description=f"Connection Quality: **{overall_indicator['text']}**",
                color=overall_indicator["color"]
            )

            # API Latency field
            embed.add_field(
                name=f"{api_quality['emoji']} Discord API Latency",
                value=f"**{api_latency_ms}ms**\n{api_quality['description']}",
                inline=True
            )

            # WebSocket Latency field
            embed.add_field(
                name=f"{ws_quality['emoji']} WebSocket Latency",
                value=f"**{websocket_latency_ms}ms**\n{ws_quality['description']}",
                inline=True
            )

            # Add empty field for layout
            embed.add_field(name="\u200b", value="\u200b", inline=True)

            # Additional info
            embed.add_field(
                name="📊 Connection Details",
                value=(
                    f"**Shard:** {ctx.guild.shard_id if ctx.guild else 'N/A'}\n"
                    f"**Gateway:** {ctx.bot.user.id % 1000}\n"
                    f"**Timestamp:** <t:{int(time.time())}:T>"
                ),
                inline=False
            )

            embed.set_footer(text="SimiluBot Network Diagnostics")
            embed.timestamp = discord.utils.utcnow()

            await ctx.send(embed=embed)

        except discord.HTTPException as e:
            self.logger.warning(f"Discord API error during ping command: {e}")
            error_embed = discord.Embed(
                title="❌ Network Error",
                description="Failed to measure API latency due to Discord API issues.",
                color=discord.Color.red()
            )
            error_embed.add_field(
                name="WebSocket Latency",
                value=f"{round(ctx.bot.latency * 1000, 2)}ms",
                inline=True
            )
            error_embed.add_field(
                name="Error Details",
                value=f"HTTP {e.status}: {e.text}",
                inline=False
            )
            await ctx.send(embed=error_embed)

        except Exception as e:
            self.logger.error(f"Unexpected error in ping command: {e}", exc_info=True)
            error_embed = discord.Embed(
                title="❌ Ping Failed",
                description="An unexpected error occurred while measuring latency.",
                color=discord.Color.red()
            )
            error_embed.add_field(
                name="Error",
                value=str(e)[:1024],  # Limit error message length
                inline=False
            )
            await ctx.send(embed=error_embed)

    def _get_latency_quality(self, latency_ms: float) -> dict:
        """
        Determine connection quality based on latency.

        Args:
            latency_ms: Latency in milliseconds

        Returns:
            Dictionary with quality information including emoji, description, and level
        """
        if latency_ms < 0:
            return {
                "emoji": "⚠️",
                "description": "Invalid measurement",
                "level": 0
            }
        elif latency_ms <= 50:
            return {
                "emoji": "🟢",
                "description": "Excellent",
                "level": 4
            }
        elif latency_ms <= 100:
            return {
                "emoji": "🟡",
                "description": "Good",
                "level": 3
            }
        elif latency_ms <= 200:
            return {
                "emoji": "🟠",
                "description": "Fair",
                "level": 2
            }
        elif latency_ms <= 500:
            return {
                "emoji": "🔴",
                "description": "Poor",
                "level": 1
            }
        else:
            return {
                "emoji": "🔴",
                "description": "Very Poor",
                "level": 0
            }

    def _get_quality_indicator(self, quality_level: int) -> dict:
        """
        Get overall quality indicator based on quality level.

        Args:
            quality_level: Quality level (0-4)

        Returns:
            Dictionary with overall quality information
        """
        if quality_level >= 4:
            return {
                "emoji": "🟢",
                "text": "Excellent",
                "color": discord.Color.green()
            }
        elif quality_level >= 3:
            return {
                "emoji": "🟡",
                "text": "Good",
                "color": discord.Color.gold()
            }
        elif quality_level >= 2:
            return {
                "emoji": "🟠",
                "text": "Fair",
                "color": discord.Color.orange()
            }
        elif quality_level >= 1:
            return {
                "emoji": "🔴",
                "text": "Poor",
                "color": discord.Color.red()
            }
        else:
            return {
                "emoji": "⚠️",
                "text": "Critical",
                "color": discord.Color.dark_red()
            }

    def get_command_count(self) -> int:
        """
        Get the number of registered general commands.

        Returns:
            Number of commands registered by this module
        """
        return 4  # about, help, status, ping
