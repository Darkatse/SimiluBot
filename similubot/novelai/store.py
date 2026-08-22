"""SQLite persistence for NovelAI user choices and guild policy."""

from __future__ import annotations

import asyncio
import sqlite3
from dataclasses import dataclass, fields
from pathlib import Path

from .domain import UserSettings, normalize_macro_name


@dataclass(frozen=True)
class ArtistMacro:
    name: str
    value: str


@dataclass(frozen=True)
class GuildPolicy:
    guild_id: str
    enabled: bool = True
    user_mode: str = "allowlist"
    channel_mode: str = "all"


class NaiStore:
    def __init__(self, path: str):
        self.path = Path(path)

    async def initialize(self) -> None:
        await asyncio.to_thread(self._initialize)

    async def get_settings(self, user_id: str) -> UserSettings:
        def read() -> UserSettings:
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT * FROM nai_user_settings WHERE user_id = ?", (str(user_id),)
                ).fetchone()
            return (
                UserSettings(str(user_id)) if row is None else UserSettings(**dict(row))
            )

        return await asyncio.to_thread(read)

    async def save_settings(self, settings: UserSettings) -> None:
        columns = [field.name for field in fields(UserSettings)]
        values = [getattr(settings, column) for column in columns]

        def write() -> None:
            with self._connect() as connection:
                connection.execute(
                    f"INSERT INTO nai_user_settings ({', '.join(columns)}) "
                    f"VALUES ({', '.join('?' for _ in columns)}) "
                    f"ON CONFLICT(user_id) DO UPDATE SET "
                    + ", ".join(
                        f"{column} = excluded.{column}" for column in columns[1:]
                    ),
                    values,
                )

        await asyncio.to_thread(write)

    async def save_macro(self, user_id: str, name: str, value: str) -> ArtistMacro:
        macro = ArtistMacro(normalize_macro_name(name), value.strip())
        if not macro.value:
            raise ValueError("画师串内容不能为空")

        def write() -> None:
            with self._connect() as connection:
                connection.execute(
                    "INSERT INTO nai_artist_macros (user_id, name, value) VALUES (?, ?, ?) "
                    "ON CONFLICT(user_id, name) DO UPDATE SET value = excluded.value",
                    (str(user_id), macro.name, macro.value),
                )

        await asyncio.to_thread(write)
        return macro

    async def delete_macro(self, user_id: str, name: str) -> bool:
        def write() -> bool:
            with self._connect() as connection:
                cursor = connection.execute(
                    "DELETE FROM nai_artist_macros WHERE user_id = ? AND name = ?",
                    (str(user_id), normalize_macro_name(name)),
                )
                return cursor.rowcount > 0

        return await asyncio.to_thread(write)

    async def list_macros(self, user_id: str) -> tuple[ArtistMacro, ...]:
        def read() -> tuple[ArtistMacro, ...]:
            with self._connect() as connection:
                rows = connection.execute(
                    "SELECT name, value FROM nai_artist_macros WHERE user_id = ? ORDER BY name",
                    (str(user_id),),
                ).fetchall()
            return tuple(ArtistMacro(**dict(row)) for row in rows)

        return await asyncio.to_thread(read)

    async def get_policy(self, guild_id: str) -> GuildPolicy:
        def read() -> GuildPolicy:
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT guild_id, enabled, user_mode, channel_mode FROM nai_guild_policy "
                    "WHERE guild_id = ?",
                    (str(guild_id),),
                ).fetchone()
            if row is None:
                return GuildPolicy(str(guild_id))
            return GuildPolicy(
                row["guild_id"],
                bool(row["enabled"]),
                row["user_mode"],
                row["channel_mode"],
            )

        return await asyncio.to_thread(read)

    async def save_policy(self, policy: GuildPolicy) -> None:
        if policy.user_mode not in {"allowlist", "everyone"}:
            raise ValueError("成员模式必须是白名单或所有成员")
        if policy.channel_mode not in {"allowlist", "all"}:
            raise ValueError("频道模式必须是白名单或所有频道")

        def write() -> None:
            with self._connect() as connection:
                connection.execute(
                    "INSERT INTO nai_guild_policy (guild_id, enabled, user_mode, channel_mode) "
                    "VALUES (?, ?, ?, ?) ON CONFLICT(guild_id) DO UPDATE SET "
                    "enabled = excluded.enabled, user_mode = excluded.user_mode, "
                    "channel_mode = excluded.channel_mode",
                    (
                        str(policy.guild_id),
                        policy.enabled,
                        policy.user_mode,
                        policy.channel_mode,
                    ),
                )

        await asyncio.to_thread(write)

    async def set_rule(
        self, guild_id: str, kind: str, subject_id: str, allowed: bool
    ) -> None:
        if kind not in {"user", "channel"}:
            raise ValueError("白名单类型必须是成员或频道")

        def write() -> None:
            with self._connect() as connection:
                if allowed:
                    connection.execute(
                        "INSERT OR IGNORE INTO nai_access_rules (guild_id, kind, subject_id) VALUES (?, ?, ?)",
                        (str(guild_id), kind, str(subject_id)),
                    )
                else:
                    connection.execute(
                        "DELETE FROM nai_access_rules WHERE guild_id = ? AND kind = ? AND subject_id = ?",
                        (str(guild_id), kind, str(subject_id)),
                    )

        await asyncio.to_thread(write)

    async def has_rule(
        self, guild_id: str, kind: str, subject_ids: tuple[str, ...]
    ) -> bool:
        if not subject_ids:
            return False
        placeholders = ", ".join("?" for _ in subject_ids)

        def read() -> bool:
            with self._connect() as connection:
                row = connection.execute(
                    f"SELECT 1 FROM nai_access_rules WHERE guild_id = ? AND kind = ? "
                    f"AND subject_id IN ({placeholders}) LIMIT 1",
                    (str(guild_id), kind, *map(str, subject_ids)),
                ).fetchone()
            return row is not None

        return await asyncio.to_thread(read)

    async def list_rules(self, guild_id: str, kind: str) -> tuple[str, ...]:
        def read() -> tuple[str, ...]:
            with self._connect() as connection:
                rows = connection.execute(
                    "SELECT subject_id FROM nai_access_rules WHERE guild_id = ? AND kind = ? "
                    "ORDER BY subject_id",
                    (str(guild_id), kind),
                ).fetchall()
            return tuple(row["subject_id"] for row in rows)

        return await asyncio.to_thread(read)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode = WAL;
                CREATE TABLE IF NOT EXISTS nai_user_settings (
                    user_id TEXT PRIMARY KEY,
                    model TEXT,
                    orientation TEXT,
                    guidance REAL,
                    steps INTEGER,
                    uc_preset TEXT,
                    uc_text TEXT,
                    sampler TEXT
                );
                CREATE TABLE IF NOT EXISTS nai_artist_macros (
                    user_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    value TEXT NOT NULL,
                    PRIMARY KEY (user_id, name)
                );
                CREATE TABLE IF NOT EXISTS nai_guild_policy (
                    guild_id TEXT PRIMARY KEY,
                    enabled INTEGER NOT NULL CHECK (enabled IN (0, 1)),
                    user_mode TEXT NOT NULL CHECK (user_mode IN ('allowlist', 'everyone')),
                    channel_mode TEXT NOT NULL CHECK (channel_mode IN ('allowlist', 'all'))
                );
                CREATE TABLE IF NOT EXISTS nai_access_rules (
                    guild_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    subject_id TEXT NOT NULL,
                    CHECK (kind IN ('user', 'channel')),
                    PRIMARY KEY (guild_id, kind, subject_id)
                );
                PRAGMA user_version = 1;
                """
            )
