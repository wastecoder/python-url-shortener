"""`GET /{code}`: the 302, the click it writes, and the request context that click carries."""

from http import HTTPStatus
from ipaddress import IPv4Address, IPv6Address
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from tests.fakes import InMemoryClickRepository
from tests.unit.conftest import CLIENT_ADDRESS, CLIENT_PORT, NOW
from url_shortener.adapter.web.redirect_controller import _client_address

TARGET = "https://example.com/a?x=1#top"


def _create(client: TestClient, url: str = TARGET) -> str:
    return str(client.post("/links", json={"url": url}).json()["code"])


def test_a_known_code_answers_302_with_the_destination(client: TestClient) -> None:
    """
    Given a shortened URL,
    when its code is followed,
    then the answer is 302 -- never 301, which a browser caches, and never Starlette's default
    307, which preserves the method -- and Location is the URL exactly as it was submitted.
    """
    code = _create(client)

    response = client.get(f"/{code}")

    assert response.status_code == HTTPStatus.FOUND
    assert response.headers["location"] == TARGET


def test_the_redirect_asks_not_to_be_stored(client: TestClient) -> None:
    """
    Given a shortened URL,
    when its code is followed,
    then the response asks caches not to keep it, which is the header form of the reason 302 was
    chosen over 301: every access has to reach this API to be counted.
    """
    code = _create(client)

    assert client.get(f"/{code}").headers["cache-control"] == "no-store"


def test_following_a_link_records_exactly_one_click(
    client: TestClient, clicks: InMemoryClickRepository
) -> None:
    """
    Given a shortened URL,
    when its code is followed twice,
    then two rows were appended -- clicks are counted by rows written, not by a counter updated.
    """
    code = _create(client)

    client.get(f"/{code}")
    client.get(f"/{code}")

    assert len(clicks.recorded) == 2


def test_the_recorded_click_carries_the_request_context(
    client: TestClient, clicks: InMemoryClickRepository
) -> None:
    """
    Given a request carrying a user agent and a referer,
    when the code is followed,
    then the click holds both, the peer address parsed into an address object, the id of the link
    that was followed, and the instant the clock reported.
    """
    code = _create(client)

    client.get(f"/{code}", headers={"user-agent": "curl/8.7.1", "referer": "https://news.example"})

    recorded = clicks.recorded[0]
    assert recorded.link_id == 1
    assert recorded.occurred_at == NOW
    assert recorded.user_agent == "curl/8.7.1"
    assert recorded.referer == "https://news.example"
    assert recorded.ip == IPv4Address(CLIENT_ADDRESS)


def test_headers_that_were_not_sent_are_recorded_as_absent(
    client: TestClient, clicks: InMemoryClickRepository
) -> None:
    """
    Given a request that carries neither a user agent nor a referer,
    when the code is followed,
    then the click records both as absent -- an HTTP client owes neither header, and a click
    without them is still a click.

    The headers have to be stripped from a built request rather than simply not passed: the test
    client sends a `User-Agent` of its own unless one is removed. Without this, `headers.get(...)`
    could be given a default of `""` and nothing in the suite would notice -- which is exactly the
    mutant this test exists to kill, because an absent header and an empty one are different
    values in a nullable column.
    """
    code = _create(client)

    request = client.build_request("GET", f"/{code}")
    del request.headers["user-agent"]
    client.send(request)

    assert clicks.recorded[0].user_agent is None
    assert clicks.recorded[0].referer is None


def test_an_empty_header_is_recorded_as_the_empty_string(
    client: TestClient, clicks: InMemoryClickRepository
) -> None:
    """
    Given a request that sends a referer with no value,
    when the code is followed,
    then the click records the empty string and not absence: the caller sent the header, and this
    adapter reports what arrived instead of deciding that an empty value means nothing arrived.
    """
    code = _create(client)

    client.get(f"/{code}", headers={"referer": ""})

    assert clicks.recorded[0].referer == ""


def test_an_ipv6_peer_is_recorded_as_an_ipv6_address(
    app: FastAPI, clicks: InMemoryClickRepository
) -> None:
    """
    Given a caller reaching the service over IPv6,
    when the code is followed,
    then the click carries an IPv6 address object, because the parsing happens in the adapter and
    a value the domain accepted cannot fail later against the column that stores it.
    """
    with TestClient(app, follow_redirects=False, client=("2001:db8::1", CLIENT_PORT)) as ipv6:
        code = _create(ipv6)
        ipv6.get(f"/{code}")

    assert clicks.recorded[0].ip == IPv6Address("2001:db8::1")


def test_a_peer_address_that_does_not_parse_is_recorded_as_absent(
    app: FastAPI, clicks: InMemoryClickRepository
) -> None:
    """
    Given a peer the server reports as something that is not an address,
    when the code is followed,
    then the click records no address and the redirect still answers -- losing the address is not
    a reason to refuse to send somebody where they asked to go.
    """
    with TestClient(app, follow_redirects=False, client=("not-an-address", CLIENT_PORT)) as odd:
        code = _create(odd)
        response = odd.get(f"/{code}")

    assert response.status_code == HTTPStatus.FOUND
    assert clicks.recorded[0].ip is None


@pytest.mark.parametrize("code", ["zzzzzzz", "short", "abcdef!", "favicon.ico", "robots.txt"])
def test_an_unknown_or_malformed_code_answers_404(
    client: TestClient, clicks: InMemoryClickRepository, code: str
) -> None:
    """
    Given a path that is not a link -- an unused code, a scanner probe, a browser asking for a
    favicon,
    when it reaches the catch-all,
    then it answers a 404 problem document and records nothing: a click pointing at a link that
    does not exist is a row the foreign key would refuse anyway.
    """
    response = client.get(f"/{code}")

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["type"] == "link-not-found"
    assert clicks.recorded == ()


def test_following_a_link_is_visible_in_its_details(client: TestClient) -> None:
    """
    Given a link followed twice,
    when its details are read,
    then the total is two -- the two endpoints joined up, which is the whole flow this project
    exists to demonstrate.
    """
    code = _create(client)

    client.get(f"/{code}")
    client.get(f"/{code}")

    assert client.get(f"/links/{code}").json()["total_clicks"] == 2


def test_a_request_without_a_client_records_no_address() -> None:
    """
    Given an ASGI scope carrying no client, which a server is allowed to send,
    when the address is read,
    then it is absent -- the guard is exercised here because the test client always reports a
    peer, so this branch is unreachable through an HTTP request.
    """
    scope: dict[str, Any] = {"type": "http", "headers": [], "method": "GET", "path": "/0000001"}

    assert _client_address(Request(scope)) is None


def test_a_proxy_in_front_is_what_decides_the_address_not_this_adapter(
    app: FastAPI, clicks: InMemoryClickRepository
) -> None:
    """
    Given the application behind uvicorn's proxy-header middleware, which is on by default and
    trusts loopback,
    when a loopback caller sends X-Forwarded-For,
    then the click records the address from the header -- because the server rewrote the peer
    before the request arrived here.

    This is the test that keeps the docstring of `_client_address` honest. The adapter never reads
    that header, and saying so without qualification would still be false about the process as it
    is actually run: deciding which upstream hops may be believed is the server's job, and the
    consequence is that Fase 3 has to run with `--forwarded-allow-ips=""`.
    """
    # Uvicorn annotates its middleware with the `asgiref` scope and event unions; FastAPI and the
    # test client speak Starlette's looser `ASGIApp`. The two describe the same protocol and
    # neither is assignable to the other, which is a disagreement between two libraries rather
    # than something this test can express its way out of.
    behind_proxy = ProxyHeadersMiddleware(app, trusted_hosts="127.0.0.1")  # type: ignore[arg-type]

    with TestClient(behind_proxy, follow_redirects=False, client=("127.0.0.1", 5555)) as proxied:  # type: ignore[arg-type]
        code = _create(proxied)
        proxied.get(f"/{code}", headers={"x-forwarded-for": "203.0.113.9"})

    assert clicks.recorded[0].ip == IPv4Address("203.0.113.9")
