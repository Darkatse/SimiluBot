"""Discord slash commands for NovelAI image generation."""

from __future__ import annotations

import io
import logging
from dataclasses import replace
from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands

from similubot.auth.authorization_manager import AuthorizationManager
from similubot.novelai.client import NovelAIError
from similubot.novelai.domain import SAMPLERS, UnknownMacros, resolve_settings
from similubot.novelai.service import NaiService, NaiUserError

Model = Literal[
    "nai-diffusion-5-curated",
    "nai-diffusion-5-full",
    "nai-diffusion-4-5-curated",
    "nai-diffusion-4-5-full",
]
Orientation = Literal["portrait", "landscape", "square"]
UcPreset = Literal["heavy", "light", "furry", "human", "none"]
Sampler = Literal[
    "k_euler_ancestral",
    "k_euler",
    "k_dpmpp_2s_ancestral",
    "k_dpmpp_2m",
    "k_dpmpp_sde",
]


@app_commands.guild_only()
class NaiCog(
    commands.GroupCog, group_name="nai", group_description="NovelAI image generation"
):
    defaults = app_commands.Group(
        name="defaults", description="Your generation defaults"
    )
    artist = app_commands.Group(
        name="artist", description="Your reusable artist strings"
    )
    admin = app_commands.Group(name="admin", description="NovelAI access policy")

    def __init__(
        self,
        service: NaiService,
        auth_manager: AuthorizationManager,
    ):
        self.service = service
        self.auth_manager = auth_manager
        self.logger = logging.getLogger("similubot.commands.nai")

    @app_commands.command(description="Generate one image with your saved defaults")
    @app_commands.describe(
        prompt="Prompt; use $name$ for a saved artist string",
        guidance="CFG guidance (0-10)",
        steps="Sampling steps (1-50; above 28 may spend Anlas)",
        uc="Custom undesired-content prompt for this image",
        seed="0-4294967295; omit for a random seed",
        allow_paid="Admins only: allow a request that may spend Anlas",
    )
    async def draw(
        self,
        interaction: discord.Interaction,
        prompt: app_commands.Range[str, 1, 2000],
        model: Model | None = None,
        orientation: Orientation | None = None,
        guidance: app_commands.Range[float, 0, 10] | None = None,
        steps: app_commands.Range[int, 1, 50] | None = None,
        uc_preset: UcPreset | None = None,
        uc: app_commands.Range[str, 0, 2000] | None = None,
        sampler: Sampler | None = None,
        seed: app_commands.Range[int, 0, 4294967295] | None = None,
        allow_paid: bool = False,
    ) -> None:
        admin = self._is_admin(interaction)
        if allow_paid and not admin:
            await interaction.response.send_message(
                "Only a configured admin may allow paid generation.", ephemeral=True
            )
            return
        if not await self._can_generate(interaction, admin):
            await interaction.response.send_message(
                "NovelAI is not enabled for you in this channel.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        result = await self.service.generate(
            str(interaction.user.id),
            str(prompt),
            {
                "model": model,
                "orientation": orientation,
                "guidance": guidance,
                "steps": steps,
                "uc_preset": uc_preset,
                "uc_text": uc,
                "sampler": sampler,
                "seed": seed,
            },
            allow_paid=allow_paid,
        )
        settings = result.prepared.settings
        image = result.images[0]
        embed = discord.Embed(
            title="NovelAI",
            description=self._clip(result.prepared.original_prompt, 4096),
            color=discord.Color.blurple(),
        )
        embed.add_field(name="Model", value=settings.profile.label)
        embed.add_field(name="Size", value=f"{settings.size[0]}×{settings.size[1]}")
        embed.add_field(
            name="Guidance / Steps", value=f"{settings.guidance:g} / {settings.steps}"
        )
        embed.add_field(name="Sampler", value=SAMPLERS[settings.sampler])
        embed.add_field(name="UC", value=settings.uc_preset.title())
        embed.add_field(name="Seed", value=str(settings.seed))
        embed.set_footer(text=f"Requested by {interaction.user.display_name}")
        filename = f"novelai-{settings.seed}.png"
        embed.set_image(url=f"attachment://{filename}")
        message = await interaction.channel.send(
            embed=embed,
            file=discord.File(io.BytesIO(image), filename=filename),
            allowed_mentions=discord.AllowedMentions.none(),
        )
        await interaction.edit_original_response(
            content=f"Generated: {message.jump_url}"
        )

    @defaults.command(
        name="show", description="Show the defaults currently applied to you"
    )
    async def defaults_show(self, interaction: discord.Interaction) -> None:
        if not await self._can_use_settings(interaction):
            return
        saved, changed = await self.service.get_settings(str(interaction.user.id))
        effective = resolve_settings(saved, self.service.default_model)
        lines = [
            f"Model: **{effective.profile.label}**",
            f"Orientation: **{effective.orientation}** ({effective.size[0]}×{effective.size[1]})",
            f"Guidance: **{effective.guidance:g}**",
            f"Steps: **{effective.steps}**",
            f"UC: **{effective.uc_preset}**"
            + (" (custom text)" if saved.uc_text is not None else ""),
            f"Sampler: **{SAMPLERS[effective.sampler]}**",
        ]
        if changed:
            lines.append("Reset unsupported saved values: " + ", ".join(changed))
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @defaults.command(
        name="set", description="Change one or more of your generation defaults"
    )
    async def defaults_set(
        self,
        interaction: discord.Interaction,
        model: Model | None = None,
        orientation: Orientation | None = None,
        guidance: app_commands.Range[float, 0, 10] | None = None,
        steps: app_commands.Range[int, 1, 50] | None = None,
        uc_preset: UcPreset | None = None,
        uc: app_commands.Range[str, 0, 2000] | None = None,
        sampler: Sampler | None = None,
    ) -> None:
        if not await self._can_use_settings(interaction):
            return
        updates = {
            "model": model,
            "orientation": orientation,
            "guidance": guidance,
            "steps": steps,
            "uc_preset": uc_preset,
            "uc_text": uc,
            "sampler": sampler,
        }
        if all(value is None for value in updates.values()):
            await interaction.response.send_message(
                "Choose at least one setting to change.", ephemeral=True
            )
            return
        settings = await self.service.update_settings(
            str(interaction.user.id), **updates
        )
        await interaction.response.send_message(
            f"Defaults saved: {settings.profile.label}, {settings.orientation}, "
            f"guidance {settings.guidance:g}, {settings.steps} steps, UC {settings.uc_preset}.",
            ephemeral=True,
        )

    @defaults.command(name="reset", description="Reset one default or all of them")
    async def defaults_reset(
        self,
        interaction: discord.Interaction,
        setting: Literal[
            "all", "model", "orientation", "guidance", "steps", "uc", "sampler"
        ] = "all",
    ) -> None:
        if not await self._can_use_settings(interaction):
            return
        settings = await self.service.reset_settings(str(interaction.user.id), setting)
        await interaction.response.send_message(
            f"Reset {setting}; effective model is {settings.profile.label}.",
            ephemeral=True,
        )

    @artist.command(name="save", description="Save $name$ as a reusable artist string")
    async def artist_save(
        self,
        interaction: discord.Interaction,
        name: app_commands.Range[str, 1, 32],
        value: app_commands.Range[str, 1, 2000],
    ) -> None:
        if not await self._can_use_settings(interaction):
            return
        macro = await self.service.save_macro(
            str(interaction.user.id), str(name), str(value)
        )
        await interaction.response.send_message(
            f"Saved `${macro.name}$`.", ephemeral=True
        )

    @artist.command(name="delete", description="Delete one of your artist strings")
    async def artist_delete(
        self, interaction: discord.Interaction, name: app_commands.Range[str, 1, 32]
    ) -> None:
        if not await self._can_use_settings(interaction):
            return
        deleted = await self.service.delete_macro(str(interaction.user.id), str(name))
        text = (
            "Artist string deleted."
            if deleted
            else "No artist string with that name exists."
        )
        await interaction.response.send_message(text, ephemeral=True)

    @artist.command(name="list", description="List your saved artist strings")
    async def artist_list(self, interaction: discord.Interaction) -> None:
        if not await self._can_use_settings(interaction):
            return
        macros = await self.service.list_macros(str(interaction.user.id))
        text = (
            "\n".join(f"`${macro.name}$` → {macro.value}" for macro in macros)
            or "No artist strings saved."
        )
        await interaction.response.send_message(
            self._clip(text, 2000),
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @app_commands.command(
        description="Show the shared NovelAI account's generation allowance"
    )
    async def quota(self, interaction: discord.Interaction) -> None:
        if not await self._can_use_settings(interaction):
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        subscription = await self.service.subscription()
        lines = [
            f"Opus generation pool: **{subscription.usage_percent}%**",
            (
                f"Subscription: **{'active' if subscription.active else 'inactive'}** "
                f"(expires <t:{subscription.expires_at}:R>)"
            ),
        ]
        if self._is_admin(interaction):
            lines.append(f"Anlas: **{subscription.anlas}**")
        await interaction.edit_original_response(content="\n".join(lines))

    @admin.command(
        name="status", description="Show NovelAI access policy and allowlists"
    )
    async def admin_status(self, interaction: discord.Interaction) -> None:
        if not await self._require_admin(interaction):
            return
        guild_id = str(interaction.guild_id)
        policy = await self.service.get_policy(guild_id)
        users = await self.service.list_access_rules(guild_id, "user")
        channels = await self.service.list_access_rules(guild_id, "channel")
        text = (
            f"Enabled: **{policy.enabled}**\nUser mode: **{policy.user_mode}**\n"
            f"Channel mode: **{policy.channel_mode}**\nUsers: "
            f"{', '.join(f'<@{item}>' for item in users) or 'none'}\nChannels: "
            f"{', '.join(f'<#{item}>' for item in channels) or 'none'}"
        )
        await interaction.response.send_message(
            self._clip(text, 2000),
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @admin.command(name="policy", description="Set the guild-wide NovelAI access modes")
    async def admin_policy(
        self,
        interaction: discord.Interaction,
        enabled: bool | None = None,
        user_mode: Literal["allowlist", "everyone"] | None = None,
        channel_mode: Literal["allowlist", "all"] | None = None,
    ) -> None:
        if not await self._require_admin(interaction):
            return
        if enabled is None and user_mode is None and channel_mode is None:
            await interaction.response.send_message(
                "Choose at least one policy value.", ephemeral=True
            )
            return
        policy = await self.service.get_policy(str(interaction.guild_id))
        policy = replace(
            policy,
            enabled=policy.enabled if enabled is None else enabled,
            user_mode=user_mode or policy.user_mode,
            channel_mode=channel_mode or policy.channel_mode,
        )
        await self.service.save_policy(policy)
        await interaction.response.send_message(
            "NovelAI access policy saved.", ephemeral=True
        )

    @admin.command(name="allow", description="Allow one user or channel")
    async def admin_allow(
        self,
        interaction: discord.Interaction,
        user: discord.Member | None = None,
        channel: discord.TextChannel | None = None,
    ) -> None:
        await self._change_rule(interaction, user, channel, True)

    @admin.command(
        name="revoke", description="Remove one user or channel from its allowlist"
    )
    async def admin_revoke(
        self,
        interaction: discord.Interaction,
        user: discord.Member | None = None,
        channel: discord.TextChannel | None = None,
    ) -> None:
        await self._change_rule(interaction, user, channel, False)

    async def _change_rule(
        self,
        interaction: discord.Interaction,
        user: discord.Member | None,
        channel: discord.TextChannel | None,
        allowed: bool,
    ) -> None:
        if not await self._require_admin(interaction):
            return
        if (user is None) == (channel is None):
            await interaction.response.send_message(
                "Choose exactly one user or channel.", ephemeral=True
            )
            return
        kind, subject_id = ("user", user.id) if user else ("channel", channel.id)
        await self.service.set_access_rule(
            str(interaction.guild_id), kind, str(subject_id), allowed
        )
        await interaction.response.send_message(
            f"{kind.title()} {'allowed' if allowed else 'revoked'}.", ephemeral=True
        )

    async def _can_use_settings(self, interaction: discord.Interaction) -> bool:
        admin = self._is_admin(interaction)
        allowed = admin or await self._can_generate(interaction, False)
        if not allowed:
            await interaction.response.send_message(
                "NovelAI is not enabled for you in this guild.", ephemeral=True
            )
        return allowed

    async def _can_generate(
        self, interaction: discord.Interaction, admin: bool
    ) -> bool:
        channel_ids = [str(interaction.channel_id)]
        if parent_id := getattr(interaction.channel, "parent_id", None):
            channel_ids.append(str(parent_id))
        return await self.service.can_generate(
            str(interaction.guild_id),
            str(interaction.user.id),
            tuple(channel_ids),
            admin=admin,
        )

    def _is_admin(self, interaction: discord.Interaction) -> bool:
        return self.auth_manager.is_admin(str(interaction.user.id))

    async def _require_admin(self, interaction: discord.Interaction) -> bool:
        if self._is_admin(interaction):
            return True
        await interaction.response.send_message(
            "This command is restricted to configured admins.", ephemeral=True
        )
        return False

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        original = getattr(error, "original", error)
        if isinstance(original, UnknownMacros):
            text = str(original)
            if original.suggestions:
                text += (
                    ". Did you mean "
                    + ", ".join(
                        f"${source}$ → ${target}$"
                        for source, target in original.suggestions.items()
                    )
                    + "?"
                )
        elif isinstance(original, NovelAIError):
            text = str(original)
            if original.correlation_id:
                text += f" (request {original.correlation_id})"
        elif isinstance(original, (NaiUserError, ValueError)):
            text = str(original)
        else:
            self.logger.error(
                "Unhandled /nai error: %s",
                original,
                exc_info=(type(original), original, original.__traceback__),
            )
            text = "NovelAI command failed. The error was logged."
        if interaction.response.is_done():
            await interaction.edit_original_response(content=text)
        else:
            await interaction.response.send_message(text, ephemeral=True)

    @staticmethod
    def _clip(value: str, length: int) -> str:
        return value if len(value) <= length else value[: length - 1] + "…"
