"""Polite HTTP (PLAN §4.12): per-source limits, adaptive per-host spacing, exponential backoff with full jitter,
Retry-After, a descriptive generic User-Agent, and no personal data in any header.

Spacing is adaptive (ADR-0023): a host starts at the connector's `min_interval` between request starts; a 429 or
5xx doubles its interval (up to 10 s), and each clean answer shrinks it back by 10 % toward the floor. The client is
thread-safe, so a connector with `concurrency` > 1 keeps that many requests in flight while starts stay spaced.

A source whose server keeps state per session (`stateless=True`) gets every request on a fresh session: cookies
are dropped after each answer.

Some government hosts reset non-browser clients; a source opts into `BROWSER_UA` in the registry, and its recon
note records why.
"""

from __future__ import annotations

import random
import threading
import time
from collections.abc import Callable, Mapping
from http.cookiejar import CookieJar, DefaultCookiePolicy
from typing import Any
from urllib.parse import urlsplit

import httpx

from fin import __version__

DEFAULT_UA = f"lastro-fin/{__version__} (personal research archiver)"
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
        stateless: bool = False,
        cookies: bool = True,
        busy: bytes | None = None,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.min_interval = min_interval
        self._interval: dict[str, float] = {}
        self._lock = threading.Lock()
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.backoff_cap = backoff_cap
        self._sleep = sleep
        self._clock = clock
        self.stateless = stateless
        # a server that answers 200 with a short 'too busy' page (RAD: 297 bytes, measured 2026-11-08) is treated as a
        # 503: slower spacing and a retry, never a quiet 'absent'
        self.busy = busy
        self._last: dict[str, float] = {}
        # cookies=False: a jar that accepts none, so concurrent requests never share a server session (ASP.NET
        # serialises the requests of one session: RAD ran 4 workers at the pace of 1, measured 2026-11-08)
        jar = None if cookies else CookieJar(policy=DefaultCookiePolicy(allowed_domains=[]))
        self._client = httpx.Client(
            headers={"User-Agent": user_agent},
            cookies=jar,
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
            if self.stateless:  # no session survives a request (ANBIMA's ima-sh answers the first date of a session)
                self._client.cookies.clear()
            busy = (
                self.busy is not None and resp.status_code == 200 and len(resp.content) < 4096
                and self.busy in resp.content
            )  # fmt: skip
            if resp.status_code in RETRY_STATUS or busy:
                self._slower(host)
                if attempt < self.max_retries:
                    self._backoff(attempt, resp.headers.get("Retry-After"))
                    continue
            else:
                self._faster(host)
            return resp
        raise FetchError(url, f"gave up after {self.max_retries + 1} attempts: {last_exc!r}")

    MAX_INTERVAL = 10.0

    def _space(self, host: str) -> None:
        """Reserve the next start slot for `host` under the lock, then wait for it outside the lock."""
        with self._lock:
            interval = self._interval.get(host, self.min_interval)
            now = self._clock()
            start = max(now, self._last.get(host, float("-inf")) + interval)
            self._last[host] = start
        if start > now:
            self._sleep(start - now)

    def _slower(self, host: str) -> None:
        with self._lock:
            cur = self._interval.get(host, self.min_interval)
            self._interval[host] = min(self.MAX_INTERVAL, max(cur * 2, 0.5))

    def _faster(self, host: str) -> None:
        with self._lock:
            cur = self._interval.get(host, self.min_interval)
            if cur > self.min_interval:
                self._interval[host] = max(self.min_interval, cur * 0.9)

    def _backoff(self, attempt: int, retry_after: str | None) -> None:
        if retry_after is not None and retry_after.isdigit():
            delay = min(float(retry_after), self.backoff_cap)
        else:
            delay = random.uniform(0, min(self.backoff_cap, self.backoff_base * 2**attempt))
        self._sleep(delay)
