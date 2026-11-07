"""Polite HTTP (PLAN §4.12): per-host spacing, exponential backoff with full jitter, Retry-After, a descriptive
generic User-Agent, and no personal data in any header.

Some government hosts reset non-browser clients; a source opts into `BROWSER_UA` in the registry, and its recon
note records why.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable, Mapping
from typing import Any
from urllib.parse import urlsplit

import httpx

from fin import __version__

DEFAULT_UA = f"lastro-fin/{__version__} (personal research archiver; low request rate)"
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)
RETRY_STATUS = frozenset({429, 500, 502, 503, 504})


class FetchError(RuntimeError):
    def __init__(self, url: str, message: str, status: int | None = None) -> None:
        super().__init__(f"{url}: {message}")
        self.url = url
        self.status = status


class PoliteClient:
    def __init__(
        self,
        *,
        user_agent: str = DEFAULT_UA,
        min_interval: float = 1.0,
        max_retries: int = 5,
        backoff_base: float = 2.0,
        backoff_cap: float = 120.0,
        timeout: float = 120.0,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.min_interval = min_interval
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.backoff_cap = backoff_cap
        self._sleep = sleep
        self._clock = clock
        self._last: dict[str, float] = {}
        self._client = httpx.Client(
            headers={"User-Agent": user_agent},
            timeout=timeout,
            follow_redirects=True,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def request(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        data: Mapping[str, Any] | None = None,
        json: Any = None,
        content: bytes | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        host = urlsplit(url).netloc
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            self._space(host)
            try:
                resp = self._client.request(
                    method, url, params=params, data=data, json=json, content=content, headers=headers
                )
            except httpx.TransportError as e:
                last_exc = e
                if attempt < self.max_retries:
                    self._backoff(attempt, None)
                continue
            if resp.status_code in RETRY_STATUS and attempt < self.max_retries:
                self._backoff(attempt, resp.headers.get("Retry-After"))
                continue
            return resp
        raise FetchError(url, f"gave up after {self.max_retries + 1} attempts: {last_exc!r}")

    def _space(self, host: str) -> None:
        wait = self._last.get(host, float("-inf")) + self.min_interval - self._clock()
        if wait > 0:
            self._sleep(wait)
        self._last[host] = self._clock()

    def _backoff(self, attempt: int, retry_after: str | None) -> None:
        if retry_after is not None and retry_after.isdigit():
            delay = min(float(retry_after), self.backoff_cap)
        else:
            delay = random.uniform(0, min(self.backoff_cap, self.backoff_base * 2**attempt))
        self._sleep(delay)
