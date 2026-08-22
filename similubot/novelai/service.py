"""NovelAI application service: policy, settings, quota, and generation."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from typing import Any

from .client import NovelAIClient, Subscription
from .domain import (
    EffectiveSettings,
    PreparedGeneration,
    UserSettings,
    free_generation_reasons,
    get_profile,
    normalize_saved_settings,
    prepare_generation,
    reset_settings,
    resolve_settings,
)
from .store import ArtistMacro, GuildPolicy, NaiStore


class NaiUserError(ValueError):
    """An expected error that can be shown directly to a Discord user."""


@dataclass(frozen=True)
class GenerationResult:
    prepared: PreparedGeneration
    images: tuple[bytes, ...]
    subscription: Subscription


class NaiService:
    def __init__(self, client: NovelAIClient, store: NaiStore, default_model: str):
        self.client = client
        self.store = store
        self.default_model = get_profile(default_model).model_id
        # ponytail: one account has one generation lane; add a queue only if contention becomes real.
        self._generation_lock = asyncio.Lock()

    async def initialize(self) -> None:
        await self.store.initialize()

    async def close(self) -> None:
        await self.client.close()

    async def get_settings(self, user_id: str) -> tuple[UserSettings, tuple[str, ...]]:
        saved = await self.store.get_settings(user_id)
        normalized, changed = normalize_saved_settings(saved)
        if changed:
            await self.store.save_settings(normalized)
        return normalized, changed

    async def update_settings(self, user_id: str, **updates: Any) -> EffectiveSettings:
        saved, _ = await self.get_settings(user_id)
        changes = {key: value for key, value in updates.items() if value is not None}
        if "uc_preset" in changes and "uc_text" not in changes:
            changes["uc_text"] = None
        candidate = replace(saved, **changes)
        effective = resolve_settings(candidate, self.default_model)
        await self.store.save_settings(candidate)
        return effective

    async def reset_settings(self, user_id: str, field_name: str) -> EffectiveSettings:
        saved, _ = await self.get_settings(user_id)
        if field_name == "uc":
            saved = replace(saved, uc_preset=None, uc_text=None)
        else:
            saved = reset_settings(saved, field_name)
        await self.store.save_settings(saved)
        return resolve_settings(saved, self.default_model)

    async def save_macro(self, user_id: str, name: str, value: str) -> ArtistMacro:
        return await self.store.save_macro(user_id, name, value)

    async def delete_macro(self, user_id: str, name: str) -> bool:
        return await self.store.delete_macro(user_id, name)

    async def list_macros(self, user_id: str) -> tuple[ArtistMacro, ...]:
        return await self.store.list_macros(user_id)

    async def subscription(self) -> Subscription:
        return await self.client.subscription()

    async def can_generate(
        self,
        guild_id: str,
        user_id: str,
        channel_ids: tuple[str, ...],
        *,
        admin: bool,
    ) -> bool:
        policy = await self.store.get_policy(guild_id)
        if not policy.enabled:
            return False
        if admin:
            return True
        user_allowed = policy.user_mode == "everyone" or await self.store.has_rule(
            guild_id, "user", (user_id,)
        )
        channel_allowed = policy.channel_mode == "all" or await self.store.has_rule(
            guild_id, "channel", channel_ids
        )
        return user_allowed and channel_allowed

    async def generate(
        self,
        user_id: str,
        prompt: str,
        overrides: dict[str, Any],
        *,
        allow_paid: bool = False,
    ) -> GenerationResult:
        saved, _ = await self.get_settings(user_id)
        settings = resolve_settings(saved, self.default_model, overrides)
        macros = {
            macro.name: macro.value for macro in await self.store.list_macros(user_id)
        }
        prepared = prepare_generation(prompt, settings, macros)
        if self._generation_lock.locked():
            raise NaiUserError("NovelAI 正在生成另一张图片，请稍后再试")

        async with self._generation_lock:
            subscription = await self.client.subscription()
            paid_reasons = free_generation_reasons(
                settings,
                subscription.tier,
                subscription.active,
                subscription.usage_available,
            )
            if paid_reasons and not allow_paid:
                raise NaiUserError("本次请求可能消耗 Anlas：" + "；".join(paid_reasons))
            images = await self.client.generate(prepared.payload)
        return GenerationResult(prepared, images, subscription)

    async def get_policy(self, guild_id: str) -> GuildPolicy:
        return await self.store.get_policy(guild_id)

    async def save_policy(self, policy: GuildPolicy) -> None:
        await self.store.save_policy(policy)

    async def set_access_rule(
        self, guild_id: str, kind: str, subject_id: str, allowed: bool
    ) -> None:
        await self.store.set_rule(guild_id, kind, subject_id, allowed)

    async def list_access_rules(self, guild_id: str, kind: str) -> tuple[str, ...]:
        return await self.store.list_rules(guild_id, kind)
