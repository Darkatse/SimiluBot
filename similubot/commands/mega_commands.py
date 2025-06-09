"""MEGA download and conversion commands."""
import asyncio
import logging
import os
from typing import Optional, Tuple
import discord
from discord.ext import commands

from similubot.core.command_registry import CommandRegistry
from similubot.downloaders.mega_downloader import MegaDownloader
from similubot.converters.audio_converter import AudioConverter
from similubot.uploaders.catbox_uploader import CatboxUploader
from similubot.uploaders.discord_uploader import DiscordUploader
from similubot.progress.discord_updater import DiscordProgressUpdater
from similubot.progress.base import ProgressInfo, ProgressStatus
from similubot.utils.config_manager import ConfigManager


class MegaCommands:
    """
    MEGA download and conversion command handlers.

    Handles MEGA link processing, audio conversion, and file uploading
    with real-time progress tracking and authorization.
    """

    def __init__(
        self,
        config: ConfigManager,
        downloader: Optional[MegaDownloader],
        converter: AudioConverter,
        catbox_uploader: CatboxUploader,
        discord_uploader: DiscordUploader
    ):
        """
        Initialize MEGA commands.

        Args:
            config: Configuration manager
            downloader: MEGA downloader instance (None if MEGA is disabled)
            converter: Audio converter instance
            catbox_uploader: CatBox uploader instance
            discord_uploader: Discord uploader instance
        """
        self.logger = logging.getLogger("similubot.commands.mega")
        self.config = config
        self.downloader = downloader
        self.converter = converter
        self.catbox_uploader = catbox_uploader
        self.discord_uploader = discord_uploader

    def is_available(self) -> bool:
        """
        Check if MEGA commands are available.

        Returns:
            True if MEGA downloader is available, False otherwise
        """
        return self.downloader is not None and self.downloader.is_available()

    def register_commands(self, registry: CommandRegistry) -> None:
        """
        Register MEGA commands with the command registry.

        Args:
            registry: Command registry instance
        """
        if not self.is_available():
            self.logger.info("MEGA commands not registered (not available)")
            return

        usage_examples = [
            "!mega https://mega.nz/file/ABC123def456 - Download with default bitrate",
            "!mega https://mega.nz/file/ABC123def456 192 - Download with 192 kbps quality",
            "!mega https://mega.nz/file/ABC123def456 320 - Download with high quality (320 kbps)"
        ]

        help_text = (
            "Downloads audio/video files from MEGA and converts them to AAC format. "
            f"Files are uploaded to {self.config.get_mega_upload_service()}. "
            "Supports automatic file size optimization for CatBox uploads."
        )

        registry.register_command(
            name="mega",
            callback=self.mega_command,
            description="Download a file from MEGA and convert it to AAC",
            required_permission="mega",
            usage_examples=usage_examples,
            help_text=help_text
        )

        self.logger.debug("MEGA commands registered")

    async def mega_command(self, ctx: commands.Context, url: str, bitrate: Optional[int] = None) -> None:
        """
        Download a file from MEGA and convert it to AAC.

        Args:
            ctx: Discord command context
            url: MEGA link to download
            bitrate: AAC bitrate in kbps (optional)
        """
        if not self.is_available():
            await ctx.reply("❌ MEGA functionality is not available. Please check if MegaCMD is installed and MEGA is enabled in the configuration.")
            return

        if not self.downloader.is_mega_link(url):
            await ctx.reply("❌ Invalid MEGA link. Please provide a valid MEGA link.")
            return

        await self.process_mega_link(ctx.message, url, bitrate)

    async def process_mega_link(
        self,
        message: discord.Message,
        url: str,
        bitrate: Optional[int] = None
    ) -> None:
        """
        Process a MEGA link with real-time progress tracking.

        Args:
            message: Discord message containing the link
            url: MEGA link to process
            bitrate: AAC bitrate in kbps (optional)
        """
        if not self.is_available():
            await message.reply("❌ MEGA functionality is not available. Please check if MegaCMD is installed and MEGA is enabled in the configuration.")
            return

        # Use default bitrate if not specified
        if bitrate is None:
            bitrate = self.config.get_default_bitrate()

        # Create initial progress embed
        embed = discord.Embed(
            title="🔄 Media Processing",
            description=f"Preparing to download and convert... (bitrate: {bitrate} kbps)",
            color=0x3498db
        )
        response = await message.reply(embed=embed)

        # Create Discord progress updater
        discord_updater = DiscordProgressUpdater(response, update_interval=5.0)
        progress_callback = discord_updater.create_callback()

        # Initialize variables for cleanup
        file_path: Optional[str] = None
        converted_file: Optional[str] = None

        try:
            # Step 1: Download with progress
            self.logger.info(f"Starting MEGA download: {url}")
            success, file_path, error = await asyncio.to_thread(
                self.downloader.download_with_progress,
                url,
                progress_callback
            )

            if not success or not file_path:
                await self._send_error_embed(response, "Download Failed", error or "Unknown error")
                return

            # Step 2: Convert with progress
            self.logger.info(f"Starting audio conversion: {file_path}")
            success, converted_file, error = await asyncio.to_thread(
                self.converter.convert_to_aac_with_progress,
                file_path,
                bitrate,
                None,  # Use default output file path
                progress_callback
            )

            if not success or not converted_file:
                await self._send_error_embed(response, "Conversion Failed", error or "Unknown error")
                return

            # Step 2.5: Optimize file size for CatBox if needed
            upload_service = self.config.get_mega_upload_service()
            if upload_service == "catbox":
                optimized_file, final_bitrate = await self._optimize_file_size_for_catbox(
                    file_path, converted_file, bitrate, progress_callback
                )
                if optimized_file:
                    # Clean up the original converted file if it was replaced
                    if optimized_file != converted_file and os.path.exists(converted_file):
                        try:
                            os.remove(converted_file)
                            self.logger.debug(f"Removed original converted file: {converted_file}")
                        except Exception as e:
                            self.logger.warning(f"Failed to remove original converted file: {e}")
                    converted_file = optimized_file
                    bitrate = final_bitrate
                else:
                    # Optimization failed - file is too large even at lowest bitrate
                    await self._send_error_embed(
                        response,
                        "File Too Large",
                        "The converted file exceeds CatBox's 200MB limit even at the lowest bitrate (96 kbps). "
                        "Please try a shorter audio file or use Discord upload instead."
                    )
                    return

            # Step 3: Upload with progress
            await self._upload_file(response, converted_file, bitrate, upload_service, progress_callback, message)

        except Exception as e:
            self.logger.error(f"Error processing MEGA link: {e}", exc_info=True)
            await self._send_error_embed(
                response,
                "Processing Error",
                f"An unexpected error occurred: {str(e)}"
            )

        finally:
            # Clean up temporary files
            self._cleanup_temp_files([file_path, converted_file])

    async def _upload_file(
        self,
        response: discord.Message,
        converted_file: str,
        bitrate: int,
        upload_service: str,
        progress_callback,
        original_message: discord.Message
    ) -> None:
        """Upload the converted file to the specified service."""
        self.logger.info(f"Starting upload to {upload_service}: {converted_file}")

        if upload_service == "catbox":
            success, file_url, error = await asyncio.to_thread(
                self.catbox_uploader.upload_with_progress,
                converted_file,
                progress_callback
            )

            if not success or not file_url:
                await self._send_error_embed(response, "Upload Failed", error or "Unknown error")
                return

            # Create success embed
            file_name = os.path.basename(converted_file)
            file_size = os.path.getsize(converted_file)

            success_embed = discord.Embed(
                title="✅ Processing Complete",
                description="Your file has been successfully downloaded, converted, and uploaded!",
                color=0x2ecc71
            )
            success_embed.add_field(name="📁 File", value=file_name, inline=True)
            success_embed.add_field(name="🎵 Bitrate", value=f"{bitrate} kbps", inline=True)
            success_embed.add_field(name="📊 Size", value=self._format_file_size(file_size), inline=True)
            success_embed.add_field(name="🔗 Download Link", value=file_url, inline=False)
            success_embed.timestamp = discord.utils.utcnow()

            await response.edit(embed=success_embed)

        else:  # discord upload
            success, discord_msg, error = await self.discord_uploader.upload(
                converted_file,
                original_message.channel,
                content=f"✅ Converted file ({bitrate} kbps)"
            )

            if not success:
                await self._send_error_embed(response, "Upload Failed", error or "Unknown error")
                return

            # Delete the processing message since file is uploaded directly
            await response.delete()

    async def _optimize_file_size_for_catbox(
        self,
        original_file: str,
        converted_file: str,
        current_bitrate: int,
        progress_callback
    ) -> Tuple[Optional[str], int]:
        """
        Optimize file size for CatBox upload by reducing bitrate if file is too large.

        Args:
            original_file: Path to the original downloaded file
            converted_file: Path to the currently converted file
            current_bitrate: Current bitrate used for conversion
            progress_callback: Progress callback for updates

        Returns:
            Tuple containing:
                - Path to optimized file (None if optimization failed)
                - Final bitrate used
        """
        # CatBox file size limit (200MB)
        CATBOX_SIZE_LIMIT = 200 * 1024 * 1024  # 200MB in bytes

        # Bitrate hierarchy for optimization
        BITRATE_HIERARCHY = [512, 384, 320, 256, 192, 128, 96]

        try:
            # Check current file size
            current_size = os.path.getsize(converted_file)
            self.logger.info(f"Checking file size: {self._format_file_size(current_size)} (limit: 200MB)")

            # If file is within limit, return as-is
            if current_size <= CATBOX_SIZE_LIMIT:
                self.logger.info("File size is within CatBox limit, no optimization needed")
                return converted_file, current_bitrate

            self.logger.warning(f"File size ({self._format_file_size(current_size)}) exceeds CatBox limit, starting optimization")

            # Find current bitrate position in hierarchy
            try:
                current_index = BITRATE_HIERARCHY.index(current_bitrate)
            except ValueError:
                # If current bitrate is not in hierarchy, find the closest lower one
                current_index = -1
                for i, bitrate in enumerate(BITRATE_HIERARCHY):
                    if bitrate < current_bitrate:
                        current_index = i
                        break
                if current_index == -1:
                    current_index = 0  # Start from the highest available

            # Try each lower bitrate
            for i in range(current_index + 1, len(BITRATE_HIERARCHY)):
                target_bitrate = BITRATE_HIERARCHY[i]
                self.logger.info(f"Attempting optimization with {target_bitrate} kbps bitrate")

                # Update progress
                if progress_callback:
                    progress_info = ProgressInfo(
                        operation="optimization",
                        status=ProgressStatus.IN_PROGRESS,
                        percentage=50.0,
                        message=f"🔧 Optimizing file size (trying {target_bitrate} kbps)..."
                    )
                    progress_callback(progress_info)

                # Convert with lower bitrate
                success, optimized_file, error = await asyncio.to_thread(
                    self.converter.convert_to_aac_with_progress,
                    original_file,
                    target_bitrate,
                    None,  # Use default output file path
                    progress_callback
                )

                if not success or not optimized_file:
                    self.logger.warning(f"Failed to convert with {target_bitrate} kbps: {error}")
                    continue

                # Check new file size
                new_size = os.path.getsize(optimized_file)
                self.logger.info(f"New file size with {target_bitrate} kbps: {self._format_file_size(new_size)}")

                if new_size <= CATBOX_SIZE_LIMIT:
                    self.logger.info(f"Successfully optimized file to {self._format_file_size(new_size)} with {target_bitrate} kbps")

                    # Update progress
                    if progress_callback:
                        progress_info = ProgressInfo(
                            operation="optimization",
                            status=ProgressStatus.COMPLETED,
                            percentage=100.0,
                            message=f"✅ File optimized to {target_bitrate} kbps ({self._format_file_size(new_size)})"
                        )
                        progress_callback(progress_info)

                    return optimized_file, target_bitrate
                else:
                    # File still too large, clean up and try next bitrate
                    try:
                        os.remove(optimized_file)
                        self.logger.debug(f"Removed oversized file: {optimized_file}")
                    except Exception as e:
                        self.logger.warning(f"Failed to remove oversized file: {e}")

            # If we get here, even the lowest bitrate didn't work
            self.logger.error("Failed to optimize file size even with lowest bitrate (96 kbps)")

            # Update progress with failure
            if progress_callback:
                progress_info = ProgressInfo(
                    operation="optimization",
                    status=ProgressStatus.FAILED,
                    percentage=100.0,
                    message="❌ File too large even at lowest bitrate"
                )
                progress_callback(progress_info)

            return None, current_bitrate

        except Exception as e:
            self.logger.error(f"Error during file size optimization: {e}", exc_info=True)
            return None, current_bitrate

    async def _send_error_embed(self, response: discord.Message, title: str, description: str) -> None:
        """Send an error embed."""
        embed = discord.Embed(
            title=f"❌ {title}",
            description=description,
            color=0xe74c3c
        )
        embed.timestamp = discord.utils.utcnow()
        await response.edit(embed=embed)

    def _cleanup_temp_files(self, file_paths: list) -> None:
        """Clean up temporary files."""
        for file_path in file_paths:
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    self.logger.debug(f"Cleaned up temporary file: {file_path}")
                except Exception as e:
                    self.logger.warning(f"Failed to clean up temporary file {file_path}: {e}")

    def _format_file_size(self, size_bytes: int) -> str:
        """Format file size in human-readable format."""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"
