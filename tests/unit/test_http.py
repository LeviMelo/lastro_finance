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


def test_a_200_busy_page_is_retried_not_returned() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) < 3:  # RAD's 297-byte page under load
            return httpx.Response(200, content=b"The HTTP service ... is unavailable. This could be because ...")
        return httpx.Response(200, content=b"PK" + b"x" * 5000)

    client = PoliteClient(min_interval=0, busy=b"is unavailable", transport=httpx.MockTransport(handler),
                          sleep=lambda s: None)  # fmt: skip
    resp = client.request("GET", "https://example.test/doc")
    assert resp.content.startswith(b"PK") and len(calls) == 3
