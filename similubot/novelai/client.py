"""Small asynchronous client for NovelAI's image API."""

from __future__ import annotations

import asyncio
import io
import json
import secrets
import string
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import aiohttp


@dataclass(frozen=True)
class Subscription:
    tier: int
    active: bool
    expires_at: int
    fixed_anlas: int
    purchased_anlas: int
    usage_percent: int
    usage_is_negative: bool
    time_until_next_percent: int

    @property
    def anlas(self) -> int:
        return self.fixed_anlas + self.purchased_anlas

    @property
    def usage_available(self) -> bool:
        return not self.usage_is_negative and self.usage_percent > 0


class NovelAIError(RuntimeError):
    """An error returned by NovelAI or its transport."""

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        correlation_id: str | None = None,
        detail: str | None = None,
    ):
        super().__init__(message)
        self.status = status
        self.correlation_id = correlation_id
        self.detail = detail


class NovelAIClient:
    def __init__(
        self,
        api_key: str | Callable[[], str],
        base_url: str = "https://image.novelai.net",
        timeout: int = 120,
    ):
        self._api_key = api_key if callable(api_key) else lambda: api_key
        if not self._api_key():
            raise ValueError("尚未设置 NOVELAI_KEY")
        self.base_url = base_url.rstrip("/")
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._session: aiohttp.ClientSession | None = None

    async def subscription(self) -> Subscription:
        data = await self._request_json("GET", "/user/subscription")
        steps = data["trainingStepsLeft"]
        usage = data["usage"]
        return Subscription(
            tier=int(data["tier"]),
            active=bool(data["active"]),
            expires_at=int(data["expiresAt"]),
            fixed_anlas=int(steps["fixedTrainingStepsLeft"]),
            purchased_anlas=int(steps["purchasedTrainingSteps"]),
            usage_percent=int(usage["percent"]),
            usage_is_negative=bool(usage["isNegative"]),
            time_until_next_percent=int(usage["timeUntilNextPercent"]),
        )

    async def generate(self, payload: dict[str, Any]) -> tuple[bytes, ...]:
        correlation_id = "".join(
            secrets.choice(string.ascii_letters + string.digits) for _ in range(6)
        )
        session = await self._get_session()
        try:
            for attempt in range(3):
                async with session.post(
                    f"{self.base_url}/ai/generate-image",
                    json=payload,
                    headers=self._request_headers(
                        {
                            "X-Correlation-ID": correlation_id,
                            "Accept": "application/zip",
                        }
                    ),
                ) as response:
                    body = await response.read()
                if response.status < 400:
                    break
                error = self._api_error(body, response.status, correlation_id)
                concurrent_lock = (
                    error.status == 429
                    and "concurrent generation is locked"
                    in (error.detail or "").lower()
                )
                if concurrent_lock and attempt < 2:
                    await asyncio.sleep(7)
                    continue
                raise error
        except aiohttp.ClientError as error:
            raise NovelAIError(
                "无法连接 NovelAI", correlation_id=correlation_id
            ) from error

        try:
            with zipfile.ZipFile(io.BytesIO(body)) as archive:
                images = tuple(
                    archive.read(name)
                    for name in archive.namelist()
                    if not name.endswith("/")
                )
        except zipfile.BadZipFile as error:
            raise NovelAIError(
                "NovelAI 返回了无效的图片压缩包",
                correlation_id=correlation_id,
            ) from error
        if not images:
            raise NovelAIError("NovelAI 没有返回图片", correlation_id=correlation_id)
        return images

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def _request_json(self, method: str, path: str) -> dict[str, Any]:
        session = await self._get_session()
        try:
            async with session.request(
                method,
                f"{self.base_url}{path}",
                headers=self._request_headers(),
            ) as response:
                body = await response.read()
                if response.status >= 400:
                    raise self._api_error(body, response.status)
        except aiohttp.ClientError as error:
            raise NovelAIError("无法连接 NovelAI") from error
        try:
            return json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise NovelAIError("NovelAI 返回了无效响应") from error

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self._timeout)
        return self._session

    def _request_headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        api_key = self._api_key()
        if not api_key:
            raise ValueError("尚未设置 NOVELAI_KEY")
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            **(extra or {}),
        }

    @staticmethod
    def _api_error(
        body: bytes, status: int, correlation_id: str | None = None
    ) -> NovelAIError:
        try:
            data = json.loads(body)
            detail = str(data.get("message") or data.get("error") or data)
        except (json.JSONDecodeError, UnicodeDecodeError):
            detail = body.decode("utf-8", "replace")
        message = {
            401: "NovelAI 密钥无效或已过期",
            429: "NovelAI 请求过于频繁，请稍后重试",
        }.get(status, f"NovelAI 请求失败（状态码 {status}）")
        return NovelAIError(
            message,
            status=status,
            correlation_id=correlation_id,
            detail=detail[:500],
        )
