"""Polite client: a cookie-free client never carries a server session between requests."""

from __future__ import annotations

import httpx

from fin.ingest.http import PoliteClient


def test_cookie_free_client_never_sends_a_session_cookie() -> None:
    seen: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("cookie"))
        return httpx.Response(200, headers={"Set-Cookie": "ASP.NET_SessionId=abc; path=/"}, content=b"ok")

    client = PoliteClient(min_interval=0, cookies=False, transport=httpx.MockTransport(handler), sleep=lambda s: None)
    client.request("GET", "https://example.test/a")
    client.request("GET", "https://example.test/b")
    assert seen == [None, None]
