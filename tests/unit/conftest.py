"""Fixtures for the API tests: the real application, with the driven ports swapped for fakes.

What is overridden here is deliberately narrow. Only the three **driven** ports are replaced --
the two repositories and the clock -- plus the settings, so that the short URLs are built from a
known origin. The use cases are not overridden, which means every one of these tests runs the real
`CreateLinkUseCaseImpl`, the real deduplication flow and the real wiring in `dependencies.py`.
FastAPI resolves overrides through sub-dependencies, so replacing a leaf is enough.

The app is built per test by `create_app()`. `dependency_overrides` is state on the app object, so
sharing one app across tests would leak one test's fakes into the next.
"""

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.fakes import FixedClock, InMemoryClickRepository, InMemoryLinkRepository
from url_shortener.adapter.config.dependencies import (
    get_click_repository,
    get_clock,
    get_link_repository,
)
from url_shortener.adapter.config.settings import Settings, get_settings
from url_shortener.main import create_app

BASE_URL = "https://sho.rt"
NOW = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)
# How that instant looks once Pydantic has serialised it: RFC 3339, with the UTC offset
# written as `Z` rather than as `+00:00`. Both spell the same instant; only one is what the
# API actually puts on the wire, and a test that guesses is a test that passes for the wrong
# reason.
NOW_ON_THE_WIRE = "2026-08-31T12:00:00Z"
CLIENT_ADDRESS = "203.0.113.7"
CLIENT_PORT = 51234


@pytest.fixture
def links() -> InMemoryLinkRepository:
    """The `link` table, empty."""
    return InMemoryLinkRepository()


@pytest.fixture
def clicks() -> InMemoryClickRepository:
    """The `click` table, empty."""
    return InMemoryClickRepository()


@pytest.fixture
def clock() -> FixedClock:
    """A clock frozen at a known instant, so a response body can be asserted exactly."""
    return FixedClock(NOW)


@pytest.fixture
def settings() -> Settings:
    """Settings built in the test rather than read from the environment.

    `_env_file=None` keeps a developer's local `.env` out of the run: with it, the origin the
    short URLs are built from would depend on whose machine the suite is on.
    """
    return Settings(
        _env_file=None,
        database_url="postgresql+psycopg://unused:unused@localhost:5432/unused",
        base_url=BASE_URL,
    )


@pytest.fixture
def app(
    links: InMemoryLinkRepository,
    clicks: InMemoryClickRepository,
    clock: FixedClock,
    settings: Settings,
) -> FastAPI:
    """The real application, with only its driven ports replaced."""
    application = create_app()
    application.dependency_overrides[get_link_repository] = lambda: links
    application.dependency_overrides[get_click_repository] = lambda: clicks
    application.dependency_overrides[get_clock] = lambda: clock
    application.dependency_overrides[get_settings] = lambda: settings
    return application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    """A client that never follows a redirect and reports a routable address.

    `follow_redirects=False` is not a preference. Following the `302` of a short link would make
    the test client issue a real request to the target URL, so a unit test would reach the
    network -- and would then be measuring somebody else's website.

    `client=` fixes the peer address, which is what the redirect controller reads to fill
    `Click.ip`. The default the test client reports is the literal string `testclient`, which does
    not parse as an address, so without this every click in the suite would record `None` and the
    parsing would never be exercised.
    """
    with TestClient(
        app, follow_redirects=False, client=(CLIENT_ADDRESS, CLIENT_PORT)
    ) as test_client:
        yield test_client
