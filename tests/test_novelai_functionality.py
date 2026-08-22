"""Tests that guard NovelAI protocol, persistence, and spending boundaries."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
import pytest
from discord.ext import commands

from similubot.auth.authorization_manager import AuthorizationManager
from similubot.commands.nai import NaiCog
from similubot.novelai.client import Subscription
from similubot.novelai.domain import (
    UnknownMacros,
    UserSettings,
    expand_macros,
    prepare_generation,
    resolve_settings,
)
from similubot.novelai.service import GenerationResult, NaiService, NaiUserError
from similubot.novelai.store import GuildPolicy, NaiStore


def test_slash_command_shape():
    async def scenario():
        bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
        await bot.add_cog(NaiCog(object(), AuthorizationManager(auth_enabled=False)))
        root = bot.tree.get_command("nai")
        shape = {
            command.name: {child.name for child in getattr(command, "commands", [])}
            for command in root.commands
        }
        assert shape == {
            "defaults": {"show", "set", "reset"},
            "artist": {"save", "delete", "list"},
            "admin": {"status", "policy", "allow", "revoke"},
            "draw": set(),
            "help": set(),
            "quota": set(),
        }
        await bot.close()

    asyncio.run(scenario())


def test_v5_payload_contract():
    settings = resolve_settings(
        UserSettings("42"),
        "nai-diffusion-5-curated",
        {"orientation": "landscape", "seed": 7},
    )
    generation = prepare_generation(
        "two friends, char1:[red hair] char2:[blue hair]",
        settings,
        {},
    )

    parameters = generation.payload["parameters"]
    assert generation.payload["model"] == "nai-diffusion-5-curated"
    assert parameters["params_version"] == 4
    assert (parameters["width"], parameters["height"]) == (1216, 832)
    assert parameters["tag_hint_uc_preset"] == 2
    assert parameters["straight_alpha"] is True
    assert parameters["v4_prompt"]["use_coords"] is True
    assert len(parameters["characterPrompts"]) == 2

    v45 = resolve_settings(UserSettings("42"), "nai-diffusion-4-5-curated", {"seed": 7})
    legacy_parameters = prepare_generation("1girl", v45, {}).payload["parameters"]
    assert legacy_parameters["params_version"] == 3
    assert "tag_hint_uc_preset" not in legacy_parameters

    custom_uc = UserSettings("42", uc_preset="heavy", uc_text="custom")
    one_shot = resolve_settings(
        custom_uc,
        "nai-diffusion-5-curated",
        {"uc_preset": "light", "seed": 7},
    )
    assert one_shot.uc_preset == "light"
    assert one_shot.uc_text != "custom"


def test_artist_macros_are_literal_and_single_pass():
    assert (
        expand_macros("$foo$, $$5", {"foo": "by $bar$", "bar": "ignored"})
        == "by $bar$, $5"
    )
    with pytest.raises(UnknownMacros) as error:
        expand_macros("$fob$", {"foo": "artist"})
    assert error.value.suggestions == {"fob": "foo"}


def test_sqlite_round_trip_and_access_policy(tmp_path):
    async def scenario():
        store = NaiStore(str(tmp_path / "nai.sqlite3"))
        await store.initialize()
        await store.save_settings(
            UserSettings("42", steps=25, model="nai-diffusion-5-full")
        )
        await store.save_macro("42", "$FOO$", "by artist")
        await store.save_policy(
            GuildPolicy("9", user_mode="allowlist", channel_mode="allowlist")
        )
        await store.set_rule("9", "user", "42", True)
        await store.set_rule("9", "channel", "7", True)

        assert (await store.get_settings("42")).steps == 25
        assert (await store.list_macros("42"))[0].name == "foo"
        assert await store.has_rule("9", "user", ("42",))

        service = NaiService(FakeClient(), store, "nai-diffusion-5-curated")
        assert await service.can_generate("9", "42", ("7",), admin=False)
        assert not await service.can_generate("9", "43", ("7",), admin=False)
        assert await service.can_generate("9", "43", ("8",), admin=True)

        await service.update_settings("42", uc_text="custom", uc_preset="heavy")
        effective = await service.update_settings("42", uc_preset="light", uc_text=None)
        assert effective.uc_preset == "light"
        assert (await store.get_settings("42")).uc_text is None

        await store.save_policy(GuildPolicy("9", enabled=False))
        assert not await service.can_generate("9", "42", ("7",), admin=True)

    asyncio.run(scenario())


def test_paid_request_is_stopped_before_generation(tmp_path):
    async def scenario():
        client = FakeClient(usage_percent=0)
        service = NaiService(
            client, NaiStore(str(tmp_path / "nai.sqlite3")), "nai-diffusion-5-curated"
        )
        await service.initialize()
        with pytest.raises(NaiUserError, match="可能消耗 Anlas"):
            await service.generate("42", "1girl", {"seed": 1})
        assert client.generate_calls == 0

    asyncio.run(scenario())


def test_draw_publishes_through_interaction_webhook():
    async def scenario():
        settings = resolve_settings(
            UserSettings("42"), "nai-diffusion-5-curated", {"seed": 7}
        )
        result = GenerationResult(
            prepare_generation("1girl", settings, {}),
            (b"png",),
            Subscription(3, True, 0, 10_000, 0, 100, False, 0),
        )
        service = SimpleNamespace(
            can_generate=AsyncMock(return_value=True),
            generate=AsyncMock(return_value=result),
        )
        followup = SimpleNamespace(
            send=AsyncMock(
                return_value=SimpleNamespace(jump_url="https://discord.test/message")
            )
        )
        interaction = SimpleNamespace(
            user=SimpleNamespace(id=42, display_name="Tester"),
            guild_id=9,
            channel_id=7,
            channel=SimpleNamespace(parent_id=None),
            response=SimpleNamespace(defer=AsyncMock()),
            followup=followup,
            edit_original_response=AsyncMock(),
        )
        cog = NaiCog(service, AuthorizationManager(auth_enabled=False))

        await cog.draw.callback(cog, interaction, "1girl")

        followup.send.assert_awaited_once()
        assert followup.send.await_args.kwargs["wait"] is True
        interaction.edit_original_response.assert_awaited_once_with(
            content="生成完成：https://discord.test/message"
        )

    asyncio.run(scenario())


def test_quota_hides_anlas_from_non_admins():
    async def scenario():
        service = SimpleNamespace(
            can_generate=AsyncMock(return_value=True),
            subscription=AsyncMock(
                return_value=Subscription(
                    3, True, 2_000_000_000, 8_000, 785, 72, False, 60
                )
            ),
        )

        def interaction():
            return SimpleNamespace(
                user=SimpleNamespace(id=42),
                guild_id=9,
                channel_id=7,
                channel=SimpleNamespace(parent_id=None),
                response=SimpleNamespace(defer=AsyncMock()),
                edit_original_response=AsyncMock(),
            )

        regular = interaction()
        regular_cog = NaiCog(service, AuthorizationManager(auth_enabled=False))
        await regular_cog.quota.callback(regular_cog, regular)
        regular_embed = regular.edit_original_response.await_args.kwargs["embed"]
        assert regular_embed.title == "💎 NovelAI 共享额度"
        assert all(field.name != "🪙 Anlas" for field in regular_embed.fields)

        admin = interaction()
        admin_cog = NaiCog(
            service,
            AuthorizationManager(auth_enabled=False, admin_ids=["42"]),
        )
        await admin_cog.quota.callback(admin_cog, admin)
        admin_embed = admin.edit_original_response.await_args.kwargs["embed"]
        assert (
            next(
                field.value for field in admin_embed.fields if field.name == "🪙 Anlas"
            )
            == "**8,785**"
        )

    asyncio.run(scenario())


class FakeClient:
    def __init__(self, usage_percent: int = 100):
        self.usage_percent = usage_percent
        self.generate_calls = 0

    async def subscription(self):
        return Subscription(3, True, 0, 10_000, 0, self.usage_percent, False, 0)

    async def generate(self, payload):
        self.generate_calls += 1
        return (b"png",)

    async def close(self):
        pass
