"""Authorization management commands."""
import logging
from typing import Set

import discord
from discord.ext import commands

from similubot.auth.authorization_manager import AuthorizationManager
from similubot.auth.permission_types import ModulePermission, PermissionLevel
from similubot.core.command_registry import CommandRegistry


class AuthCommands:
    """
    Authorization management command handlers.

    Provides admin commands for managing user permissions,
    viewing authorization status, and user management.
    """

    def __init__(self, auth_manager: AuthorizationManager):
        """
        Initialize authorization commands.

        Args:
            auth_manager: Authorization manager instance
        """
        self.logger = logging.getLogger("similubot.commands.auth")
        self.auth_manager = auth_manager

    def register_commands(self, registry: CommandRegistry) -> None:
        """
        Register authorization commands with the command registry.

        Args:
            registry: Command registry instance
        """
        # Define help information for the auth command group
        usage_examples = [
            "!auth status - Show authorization system status and statistics",
            "!auth user 123456789 - Show permissions for a specific user",
            "!auth add 123456789 full - Grant full access to a user",
            "!auth add 123456789 module mega_download - Grant specific module access",
            "!auth remove 123456789 - Remove user from authorization system"
        ]

        help_text = (
            "🔐 **Admin-Only Commands** - These commands require administrator privileges.\n\n"
            "The authorization system controls access to bot features and commands. "
            "Users can be granted different permission levels and access to specific modules. "
            "All authorization changes are logged and tracked for security purposes."
        )

        # Create auth command group with comprehensive help information
        auth_group = registry.register_command_group(
            name="auth",
            description="Authorization management commands (admin only)",
            admin_only=True,
            usage_examples=usage_examples,
            help_text=help_text
        )

        # Register subcommands
        registry.register_group_command(
            group=auth_group,
            name="status",
            callback=self.auth_status,
            description="Show authorization system status and statistics",
            admin_only=True
        )

        registry.register_group_command(
            group=auth_group,
            name="user",
            callback=self.auth_user,
            description="Show permissions for a specific user",
            admin_only=True
        )

        registry.register_group_command(
            group=auth_group,
            name="add",
            callback=self.auth_add,
            description="Add or update user permissions",
            admin_only=True
        )

        registry.register_group_command(
            group=auth_group,
            name="remove",
            callback=self.auth_remove,
            description="Remove user from authorization system",
            admin_only=True
        )

        self.logger.debug("Authorization commands registered")

    async def auth_status(self, ctx: commands.Context) -> None:
        """
        Show authorization system status and statistics.

        Args:
            ctx: Discord command context
        """
        stats = self.auth_manager.get_stats()

        embed = discord.Embed(
            title="🔐 Authorization System Status",
            color=0x2ecc71 if self.auth_manager.auth_enabled else 0xe74c3c
        )

        embed.add_field(
            name="System Status",
            value="🟢 Enabled" if self.auth_manager.auth_enabled else "🔴 Disabled",
            inline=True
        )

        embed.add_field(
            name="Total Users",
            value=str(stats["total_users"]),
            inline=True
        )

        embed.add_field(
            name="Admin Users",
            value=str(stats["admin_users"]),
            inline=True
        )

        embed.add_field(
            name="Full Access",
            value=str(stats["full_access_users"]),
            inline=True
        )

        embed.add_field(
            name="Module Access",
            value=str(stats["module_access_users"]),
            inline=True
        )

        embed.add_field(
            name="No Access",
            value=str(stats["no_access_users"]),
            inline=True
        )

        embed.add_field(
            name="Configuration",
            value=f"Config Path: `{self.auth_manager.config_path}`\nAdmin Notifications: {'✅' if self.auth_manager.notify_admins_on_unauthorized else '❌'}",
            inline=False
        )

        embed.timestamp = discord.utils.utcnow()
        await ctx.send(embed=embed)

    async def auth_user(self, ctx: commands.Context, user_id: str) -> None:
        """
        Show permissions for a specific user.

        Args:
            ctx: Discord command context
            user_id: Discord user ID to check
        """
        user_perms = self.auth_manager.get_user_permissions(user_id)

        if not user_perms:
            await ctx.reply(f"❌ User `{user_id}` not found in authorization system.")
            return

        # Try to get Discord user info
        try:
            discord_user = await ctx.bot.fetch_user(int(user_id))
            user_display = f"{discord_user.display_name} ({discord_user.name})"
            avatar_url = discord_user.avatar.url if discord_user.avatar else None
        except:
            user_display = "Unknown User"
            avatar_url = None

        embed = discord.Embed(
            title=f"👤 User Permissions: {user_display}",
            description=f"User ID: `{user_id}`",
            color=0x3498db
        )

        if avatar_url:
            embed.set_thumbnail(url=avatar_url)

        embed.add_field(
            name="Permission Level",
            value=user_perms.permission_level.value.title(),
            inline=True
        )

        embed.add_field(
            name="Modules",
            value=", ".join([m.value for m in user_perms.modules]) if user_perms.modules else "None",
            inline=True
        )

        embed.add_field(
            name="Admin Status",
            value="✅ Yes" if self.auth_manager.is_admin(user_id) else "❌ No",
            inline=True
        )

        # Show effective permissions
        permissions_status = []
        for module in ModulePermission:
            has_perm = user_perms.has_permission(module)
            status = "✅" if has_perm else "❌"
            permissions_status.append(f"{status} {module.value}")

        embed.add_field(
            name="Effective Permissions",
            value="\n".join(permissions_status),
            inline=False
        )

        if user_perms.notes:
            embed.add_field(
                name="Notes",
                value=user_perms.notes,
                inline=False
            )

        embed.timestamp = discord.utils.utcnow()
        await ctx.send(embed=embed)

    async def auth_add(self, ctx: commands.Context, user_id: str, level: str, *modules) -> None:
        """
        Add or update user permissions.

        Args:
            ctx: Discord command context
            user_id: Discord user ID
            level: Permission level (full, module, none)
            modules: Module permissions (for module level)
        """
        # Validate permission level
        try:
            permission_level = PermissionLevel(level.lower())
        except ValueError:
            await ctx.reply(f"❌ Invalid permission level: `{level}`. Valid levels: `full`, `module`, `none`")
            return
        if permission_level == PermissionLevel.ADMIN:
            await ctx.reply("❌ Administrators are configured in config.yaml, not through Discord commands.")
            return

        # Validate modules if provided
        module_set: Set[ModulePermission] = set()
        if modules:
            for module_name in modules:
                try:
                    module = ModulePermission(module_name.lower())
                except ValueError:
                    await ctx.reply(
                        f"❌ Invalid module: `{module_name}`. Valid modules: "
                        "`mega_download`, `ai_conversation`, `music_playback`, `general`"
                    )
                    return
                if module == ModulePermission.NOVELAI_GENERATION:
                    await ctx.reply("❌ NovelAI access is managed with `/nai admin`.")
                    return
                module_set.add(module)

        # Add/update user
        success = self.auth_manager.add_user(
            user_id=user_id,
            permission_level=permission_level,
            modules=module_set,
            notes=f"Added by {ctx.author.display_name} on {discord.utils.utcnow().strftime('%Y-%m-%d %H:%M:%S')}"
        )

        if success:
            # Try to get Discord user info
            try:
                discord_user = await ctx.bot.fetch_user(int(user_id))
                user_display = f"{discord_user.display_name} ({discord_user.name})"
            except:
                user_display = f"User ID: {user_id}"

            embed = discord.Embed(
                title="✅ User Permissions Updated",
                description=f"Successfully updated permissions for {user_display}",
                color=0x2ecc71
            )

            embed.add_field(
                name="User ID",
                value=f"`{user_id}`",
                inline=True
            )

            embed.add_field(
                name="Permission Level",
                value=permission_level.value.title(),
                inline=True
            )

            if module_set:
                embed.add_field(
                    name="Modules",
                    value=", ".join([m.value for m in module_set]),
                    inline=True
                )

            embed.add_field(
                name="Updated By",
                value=ctx.author.mention,
                inline=True
            )

            embed.timestamp = discord.utils.utcnow()
            await ctx.send(embed=embed)
        else:
            await ctx.reply(f"❌ Failed to update permissions for user `{user_id}`.")

    async def auth_remove(self, ctx: commands.Context, user_id: str) -> None:
        """
        Remove user from authorization system.

        Args:
            ctx: Discord command context
            user_id: Discord user ID to remove
        """
        # Check if user exists
        user_perms = self.auth_manager.get_user_permissions(user_id)
        if not user_perms:
            await ctx.reply(f"❌ User `{user_id}` not found in authorization system.")
            return

        # Prevent removing admin users
        if user_id in self.auth_manager.admin_ids:
            await ctx.reply(f"❌ Cannot remove admin user `{user_id}`. Remove from admin_ids in config first.")
            return

        # Remove user
        success = self.auth_manager.remove_user(user_id)

        if success:
            # Try to get Discord user info
            try:
                discord_user = await ctx.bot.fetch_user(int(user_id))
                user_display = f"{discord_user.display_name} ({discord_user.name})"
            except:
                user_display = f"User ID: {user_id}"

            embed = discord.Embed(
                title="✅ User Removed",
                description=f"Successfully removed {user_display} from authorization system",
                color=0x2ecc71
            )

            embed.add_field(
                name="User ID",
                value=f"`{user_id}`",
                inline=True
            )

            embed.add_field(
                name="Removed By",
                value=ctx.author.mention,
                inline=True
            )

            embed.timestamp = discord.utils.utcnow()
            await ctx.send(embed=embed)
        else:
            await ctx.reply(f"❌ Failed to remove user `{user_id}` from authorization system.")

    def is_available(self) -> bool:
        """
        Check if authorization commands are available.

        Returns:
            True if authorization is enabled, False otherwise
        """
        return self.auth_manager.auth_enabled
