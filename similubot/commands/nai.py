"""Discord slash commands for NovelAI image generation."""

from __future__ import annotations

import io
import logging
from dataclasses import replace

import discord
from discord import app_commands
from discord.ext import commands

from similubot.auth.authorization_manager import AuthorizationManager
from similubot.novelai.client import NovelAIError
from similubot.novelai.domain import SAMPLERS, UnknownMacros, resolve_settings
from similubot.novelai.service import NaiService, NaiUserError

MODEL_CHOICES = [
    app_commands.Choice(name="V5 Curated（精选）", value="nai-diffusion-5-curated"),
    app_commands.Choice(name="V5 Full（完整）", value="nai-diffusion-5-full"),
    app_commands.Choice(name="V4.5 Curated（精选）", value="nai-diffusion-4-5-curated"),
    app_commands.Choice(name="V4.5 Full（完整）", value="nai-diffusion-4-5-full"),
]
ORIENTATION_CHOICES = [
    app_commands.Choice(name="竖图 · 832×1216", value="portrait"),
    app_commands.Choice(name="横图 · 1216×832", value="landscape"),
    app_commands.Choice(name="方图 · 1024×1024", value="square"),
]
UC_CHOICES = [
    app_commands.Choice(name="强力", value="heavy"),
    app_commands.Choice(name="轻度", value="light"),
    app_commands.Choice(name="福瑞", value="furry"),
    app_commands.Choice(name="真人", value="human"),
    app_commands.Choice(name="无", value="none"),
]
SAMPLER_CHOICES = [
    app_commands.Choice(name=label, value=value) for value, label in SAMPLERS.items()
]
RESET_CHOICES = [
    app_commands.Choice(name=label, value=value)
    for value, label in {
        "all": "全部设置",
        "model": "模型",
        "orientation": "画布方向",
        "guidance": "引导强度",
        "steps": "采样步数",
        "uc": "负面提示词",
        "sampler": "采样器",
    }.items()
]
ORIENTATION_NAMES = {"portrait": "竖图", "landscape": "横图", "square": "方图"}
UC_NAMES = {
    "heavy": "强力",
    "light": "轻度",
    "furry": "福瑞",
    "human": "真人",
    "none": "无",
}
SETTING_NAMES = {choice.value: choice.name for choice in RESET_CHOICES}
USER_MODE_NAMES = {"allowlist": "仅白名单成员", "everyone": "所有成员"}
CHANNEL_MODE_NAMES = {"allowlist": "仅白名单频道", "all": "所有频道"}


@app_commands.guild_only()
class NaiCog(commands.GroupCog, group_name="nai", group_description="NovelAI 图像生成"):
    defaults = app_commands.Group(
        name="defaults", description="管理你的个人生图默认设置"
    )
    artist = app_commands.Group(name="artist", description="管理可复用的画师串")
    admin = app_commands.Group(name="admin", description="管理 NovelAI 使用权限")

    def __init__(
        self,
        service: NaiService,
        auth_manager: AuthorizationManager,
    ):
        self.service = service
        self.auth_manager = auth_manager
        self.logger = logging.getLogger("similubot.commands.nai")

    @app_commands.command(description="查看 NovelAI 生图指令与额度规则")
    async def help(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(
            title="🎨 Nai Chan · NovelAI 生图指南",
            description=(
                "只需填写提示词即可生图；未指定的参数会自动使用你的个人默认设置。"
            ),
            color=discord.Color.blurple(),
        )
        embed.add_field(
            name="🚀 快速开始",
            value=(
                "`/nai draw prompt:1girl, blue hair` — 生成一张图片\n"
                "`/nai quota` — 查看共享账户额度\n"
                "`/nai defaults show` — 查看当前默认设置"
            ),
            inline=False,
        )
        embed.add_field(
            name="⚙️ 个性化设置",
            value=(
                "`/nai defaults set` — 修改模型、方向、引导、步数、UC 或采样器\n"
                "`/nai defaults reset` — 恢复一项或全部默认设置\n"
                "每位 Discord 用户都有一套独立设置。"
            ),
            inline=False,
        )
        embed.add_field(
            name="🖌️ 画师串",
            value=(
                "`/nai artist save name:foo value:by artist` — 保存 `$foo$`\n"
                "`/nai artist list` · `/nai artist delete` — 查看或删除\n"
                "在提示词中写 `$foo$` 即可展开；写 `$$` 表示普通 `$`。"
            ),
            inline=False,
        )
        embed.add_field(
            name="💎 额度规则",
            value=(
                "Opus 有效、分辨率不超过 1024×1024 且步数不超过 28 时，"
                "优先使用免费生成池。可能消耗 Anlas 的请求会自动停止；"
                "只有管理员可显式允许付费生成。"
            ),
            inline=False,
        )
        if self._is_admin(interaction):
            embed.add_field(
                name="🛡️ 管理员",
                value=(
                    "`/nai admin status` — 查看权限策略\n"
                    "`/nai admin policy` — 设置成员与频道模式\n"
                    "`/nai admin allow` · `/nai admin revoke` — 管理白名单"
                ),
                inline=False,
            )
        embed.set_footer(text="帮助与设置仅对你可见")
        embed.timestamp = discord.utils.utcnow()
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(description="使用个人默认设置生成一张图片")
    @app_commands.describe(
        prompt="提示词；可用 $name$ 引用已保存的画师串",
        model="仅覆盖本次生成使用的模型",
        orientation="仅覆盖本次生成的画布方向",
        guidance="CFG 引导强度（0-10）",
        steps="采样步数（1-50；超过 28 可能消耗 Anlas）",
        uc_preset="负面提示词预设",
        uc="仅用于本次生成的自定义负面提示词",
        sampler="采样器",
        seed="随机种子（0-4294967295；留空则随机）",
        allow_paid="仅管理员：允许本次请求消耗 Anlas",
    )
    @app_commands.choices(
        model=MODEL_CHOICES,
        orientation=ORIENTATION_CHOICES,
        uc_preset=UC_CHOICES,
        sampler=SAMPLER_CHOICES,
    )
    async def draw(
        self,
        interaction: discord.Interaction,
        prompt: app_commands.Range[str, 1, 2000],
        model: str | None = None,
        orientation: str | None = None,
        guidance: app_commands.Range[float, 0, 10] | None = None,
        steps: app_commands.Range[int, 1, 50] | None = None,
        uc_preset: str | None = None,
        uc: app_commands.Range[str, 0, 2000] | None = None,
        sampler: str | None = None,
        seed: app_commands.Range[int, 0, 4294967295] | None = None,
        allow_paid: bool = False,
    ) -> None:
        admin = self._is_admin(interaction)
        if allow_paid and not admin:
            await interaction.response.send_message(
                "只有已配置的管理员可以允许付费生成。", ephemeral=True
            )
            return
        if not await self._can_generate(interaction, admin):
            await interaction.response.send_message(
                "你当前不能在此频道使用 NovelAI。", ephemeral=True
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
            title="🎨 NovelAI 生图",
            description=self._clip(result.prepared.original_prompt, 4096),
            color=discord.Color.blurple(),
        )
        embed.add_field(name="🧠 模型", value=settings.profile.label)
        embed.add_field(name="🖼️ 尺寸", value=f"{settings.size[0]}×{settings.size[1]}")
        embed.add_field(
            name="🎛️ 引导 / 步数", value=f"{settings.guidance:g} / {settings.steps}"
        )
        embed.add_field(name="🧪 采样器", value=SAMPLERS[settings.sampler])
        embed.add_field(name="🚫 负面预设", value=UC_NAMES[settings.uc_preset])
        embed.add_field(name="🎲 种子", value=str(settings.seed))
        embed.set_footer(text=f"由 {interaction.user.display_name} 生成")
        filename = f"novelai-{settings.seed}.png"
        embed.set_image(url=f"attachment://{filename}")
        message = await interaction.followup.send(
            embed=embed,
            file=discord.File(io.BytesIO(image), filename=filename),
            allowed_mentions=discord.AllowedMentions.none(),
            wait=True,
        )
        await interaction.edit_original_response(
            content=f"生成完成：{message.jump_url}"
        )

    @defaults.command(name="show", description="查看当前生效的个人默认设置")
    async def defaults_show(self, interaction: discord.Interaction) -> None:
        if not await self._can_use_settings(interaction):
            return
        saved, changed = await self.service.get_settings(str(interaction.user.id))
        effective = resolve_settings(saved, self.service.default_model)
        embed = discord.Embed(
            title="⚙️ 你的生图默认设置",
            description="`/nai draw` 未填写的参数会使用这里的值。",
            color=discord.Color.blurple(),
        )
        embed.add_field(name="🧠 模型", value=effective.profile.label, inline=True)
        embed.add_field(
            name="🖼️ 画布",
            value=(
                f"{ORIENTATION_NAMES[effective.orientation]}\n"
                f"{effective.size[0]}×{effective.size[1]}"
            ),
            inline=True,
        )
        embed.add_field(
            name="🎛️ 引导 / 步数",
            value=f"{effective.guidance:g} / {effective.steps}",
            inline=True,
        )
        embed.add_field(
            name="🧪 采样器", value=SAMPLERS[effective.sampler], inline=True
        )
        uc_name = UC_NAMES[effective.uc_preset]
        if saved.uc_text is not None:
            uc_name += " · 自定义文本"
        embed.add_field(name="🚫 负面提示词", value=uc_name, inline=True)
        if changed:
            embed.add_field(
                name="♻️ 已自动修复",
                value="、".join(SETTING_NAMES.get(item, item) for item in changed),
                inline=False,
            )
        embed.set_footer(text="使用 /nai defaults set 修改设置")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @defaults.command(name="set", description="修改一项或多项个人生图默认设置")
    @app_commands.describe(
        model="默认模型",
        orientation="默认画布方向",
        guidance="默认 CFG 引导强度（0-10）",
        steps="默认采样步数（1-50）",
        uc_preset="默认负面提示词预设",
        uc="自定义默认负面提示词",
        sampler="默认采样器",
    )
    @app_commands.choices(
        model=MODEL_CHOICES,
        orientation=ORIENTATION_CHOICES,
        uc_preset=UC_CHOICES,
        sampler=SAMPLER_CHOICES,
    )
    async def defaults_set(
        self,
        interaction: discord.Interaction,
        model: str | None = None,
        orientation: str | None = None,
        guidance: app_commands.Range[float, 0, 10] | None = None,
        steps: app_commands.Range[int, 1, 50] | None = None,
        uc_preset: str | None = None,
        uc: app_commands.Range[str, 0, 2000] | None = None,
        sampler: str | None = None,
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
                "请至少选择一项要修改的设置。", ephemeral=True
            )
            return
        settings = await self.service.update_settings(
            str(interaction.user.id), **updates
        )
        await interaction.response.send_message(
            "✅ 默认设置已保存\n"
            f"**{settings.profile.label}** · {ORIENTATION_NAMES[settings.orientation]} · "
            f"引导 {settings.guidance:g} · {settings.steps} 步 · "
            f"UC {UC_NAMES[settings.uc_preset]}",
            ephemeral=True,
        )

    @defaults.command(name="reset", description="恢复一项或全部个人默认设置")
    @app_commands.describe(setting="要恢复的设置")
    @app_commands.choices(setting=RESET_CHOICES)
    async def defaults_reset(
        self,
        interaction: discord.Interaction,
        setting: str = "all",
    ) -> None:
        if not await self._can_use_settings(interaction):
            return
        settings = await self.service.reset_settings(str(interaction.user.id), setting)
        await interaction.response.send_message(
            f"✅ 已恢复{SETTING_NAMES[setting]}；当前模型为 **{settings.profile.label}**。",
            ephemeral=True,
        )

    @artist.command(name="save", description="将 $name$ 保存为可复用的画师串")
    @app_commands.describe(name="画师串名称（无需输入 $）", value="要保存的画师提示词")
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
            f"✅ 已保存 `${macro.name}$`。", ephemeral=True
        )

    @artist.command(name="delete", description="删除一个已保存的画师串")
    @app_commands.describe(name="要删除的画师串名称")
    async def artist_delete(
        self, interaction: discord.Interaction, name: app_commands.Range[str, 1, 32]
    ) -> None:
        if not await self._can_use_settings(interaction):
            return
        deleted = await self.service.delete_macro(str(interaction.user.id), str(name))
        text = "✅ 画师串已删除。" if deleted else "没有找到这个名称的画师串。"
        await interaction.response.send_message(text, ephemeral=True)

    @artist.command(name="list", description="查看已保存的画师串")
    async def artist_list(self, interaction: discord.Interaction) -> None:
        if not await self._can_use_settings(interaction):
            return
        macros = await self.service.list_macros(str(interaction.user.id))
        text = (
            "\n".join(f"`${macro.name}$` → {macro.value}" for macro in macros)
            or "尚未保存画师串。使用 `/nai artist save` 添加一个吧。"
        )
        embed = discord.Embed(
            title="🖌️ 你的画师串",
            description=self._clip(text, 4096),
            color=discord.Color.blurple(),
        )
        embed.set_footer(text="在提示词中使用 $name$ 展开画师串")
        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @app_commands.command(description="查看共享 NovelAI 账户的生成额度")
    async def quota(self, interaction: discord.Interaction) -> None:
        if not await self._can_use_settings(interaction):
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        subscription = await self.service.subscription()
        percent = max(0, min(100, subscription.usage_percent))
        bar = "▰" * round(percent / 10) + "▱" * (10 - round(percent / 10))
        available = subscription.active and subscription.usage_available
        embed = discord.Embed(
            title="💎 NovelAI 共享额度",
            description=(
                f"`{bar}`  **{percent}%**\n"
                f"Opus 免费生成池当前**{'可用' if available else '不可用'}**。"
            ),
            color=discord.Color.green() if available else discord.Color.orange(),
        )
        tier_name = {1: "Tablet", 2: "Scroll", 3: "Opus"}.get(
            subscription.tier, f"等级 {subscription.tier}"
        )
        embed.add_field(
            name="📦 订阅",
            value=(
                f"**{tier_name} · {'有效' if subscription.active else '无效'}**\n"
                f"到期时间 <t:{subscription.expires_at}:R>"
            ),
            inline=True,
        )
        if subscription.time_until_next_percent > 0 and percent < 100:
            next_percent_at = (
                int(discord.utils.utcnow().timestamp())
                + subscription.time_until_next_percent
            )
            embed.add_field(
                name="⏳ 下次恢复",
                value=f"<t:{next_percent_at}:R>",
                inline=True,
            )
        if self._is_admin(interaction):
            embed.add_field(
                name="🪙 Anlas",
                value=f"**{subscription.anlas:,}**",
                inline=True,
            )
        embed.set_footer(text="额度信息仅对你可见 · /nai help 查看用法")
        embed.timestamp = discord.utils.utcnow()
        await interaction.edit_original_response(embed=embed)

    @admin.command(name="status", description="查看 NovelAI 权限策略与白名单")
    async def admin_status(self, interaction: discord.Interaction) -> None:
        if not await self._require_admin(interaction):
            return
        guild_id = str(interaction.guild_id)
        policy = await self.service.get_policy(guild_id)
        users = await self.service.list_access_rules(guild_id, "user")
        channels = await self.service.list_access_rules(guild_id, "channel")
        embed = discord.Embed(
            title="🛡️ NovelAI 权限策略",
            description=f"功能状态：**{'已启用' if policy.enabled else '已停用'}**",
            color=discord.Color.green() if policy.enabled else discord.Color.orange(),
        )
        embed.add_field(
            name="👥 成员模式",
            value=USER_MODE_NAMES[policy.user_mode],
            inline=True,
        )
        embed.add_field(
            name="#️⃣ 频道模式",
            value=CHANNEL_MODE_NAMES[policy.channel_mode],
            inline=True,
        )
        embed.add_field(
            name=f"成员白名单 · {len(users)}",
            value=self._clip("、".join(f"<@{item}>" for item in users) or "无", 1024),
            inline=False,
        )
        embed.add_field(
            name=f"频道白名单 · {len(channels)}",
            value=self._clip(
                "、".join(f"<#{item}>" for item in channels) or "无", 1024
            ),
            inline=False,
        )
        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @admin.command(name="policy", description="设置服务器级 NovelAI 使用策略")
    @app_commands.describe(
        enabled="是否启用 NovelAI 生图",
        user_mode="允许使用的成员范围",
        channel_mode="允许使用的频道范围",
    )
    @app_commands.choices(
        user_mode=[
            app_commands.Choice(name="仅白名单成员", value="allowlist"),
            app_commands.Choice(name="所有成员", value="everyone"),
        ],
        channel_mode=[
            app_commands.Choice(name="仅白名单频道", value="allowlist"),
            app_commands.Choice(name="所有频道", value="all"),
        ],
    )
    async def admin_policy(
        self,
        interaction: discord.Interaction,
        enabled: bool | None = None,
        user_mode: str | None = None,
        channel_mode: str | None = None,
    ) -> None:
        if not await self._require_admin(interaction):
            return
        if enabled is None and user_mode is None and channel_mode is None:
            await interaction.response.send_message(
                "请至少选择一项要修改的策略。", ephemeral=True
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
            "✅ NovelAI 权限策略已保存。", ephemeral=True
        )

    @admin.command(name="allow", description="将一个成员或频道加入白名单")
    @app_commands.describe(user="要加入白名单的成员", channel="要加入白名单的频道")
    async def admin_allow(
        self,
        interaction: discord.Interaction,
        user: discord.Member | None = None,
        channel: discord.TextChannel | None = None,
    ) -> None:
        await self._change_rule(interaction, user, channel, True)

    @admin.command(name="revoke", description="将一个成员或频道移出白名单")
    @app_commands.describe(user="要移出白名单的成员", channel="要移出白名单的频道")
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
                "请且只请选择一个成员或频道。", ephemeral=True
            )
            return
        kind, subject_id = ("user", user.id) if user else ("channel", channel.id)
        await self.service.set_access_rule(
            str(interaction.guild_id), kind, str(subject_id), allowed
        )
        subject = f"<@{subject_id}>" if kind == "user" else f"<#{subject_id}>"
        await interaction.response.send_message(
            f"✅ 已将 {subject}{'加入' if allowed else '移出'}白名单。",
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    async def _can_use_settings(self, interaction: discord.Interaction) -> bool:
        admin = self._is_admin(interaction)
        allowed = admin or await self._can_generate(interaction, False)
        if not allowed:
            await interaction.response.send_message(
                "你当前不能在此服务器使用 NovelAI。", ephemeral=True
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
            "此命令仅限已配置的管理员使用。", ephemeral=True
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
                    "。你是否想输入 "
                    + ", ".join(
                        f"${source}$ → ${target}$"
                        for source, target in original.suggestions.items()
                    )
                    + "？"
                )
        elif isinstance(original, NovelAIError):
            text = str(original)
            self.logger.warning(
                "NovelAI error: status=%s request=%s detail=%s",
                original.status,
                original.correlation_id,
                original.detail,
            )
            if original.correlation_id:
                text += f"（请求编号 {original.correlation_id}）"
        elif isinstance(original, (NaiUserError, ValueError)):
            text = str(original)
        else:
            self.logger.error(
                "Unhandled /nai error: %s",
                original,
                exc_info=(type(original), original, original.__traceback__),
            )
            text = "NovelAI 命令执行失败，错误详情已记录。"
        if interaction.response.is_done():
            await interaction.edit_original_response(content=text)
        else:
            await interaction.response.send_message(text, ephemeral=True)

    @staticmethod
    def _clip(value: str, length: int) -> str:
        return value if len(value) <= length else value[: length - 1] + "…"
