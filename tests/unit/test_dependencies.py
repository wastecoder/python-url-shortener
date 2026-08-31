"""The wiring: what is shared, what is rebuilt, and that the pieces really fit together."""

from collections.abc import Iterator

import pytest

from url_shortener.adapter.config.dependencies import (
    get_click_repository,
    get_clock,
    get_create_link_use_case,
    get_link_details_use_case,
    get_link_repository,
    get_resolve_link_use_case,
)
from url_shortener.application.viewmodel.create_link_command import CreateLinkCommand

TARGET = "https://example.com/wiring"


@pytest.fixture(autouse=True)
def empty_stores() -> Iterator[None]:
    """Drop the cached singletons around every test in this file.

    The three driven ports are `lru_cache`d on purpose -- an in-memory store rebuilt per request
    would be an empty database on every request -- and that cache is process-wide, so a test that
    writes into it would leak a link into whatever runs next.
    """
    for provider in (get_clock, get_link_repository, get_click_repository):
        provider.cache_clear()
    yield
    for provider in (get_clock, get_link_repository, get_click_repository):
        provider.cache_clear()


def test_the_driven_ports_are_shared_across_calls() -> None:
    """
    Given the repository providers,
    when each is asked twice,
    then the same object comes back, because a store rebuilt per request stores nothing.
    """
    assert get_link_repository() is get_link_repository()
    assert get_click_repository() is get_click_repository()
    assert get_clock() is get_clock()


def test_each_use_case_is_built_fresh() -> None:
    """
    Given the use case providers,
    when one is asked twice,
    then two objects come back: they hold references and nothing else, so caching them would only
    hide which collaborators each was handed.
    """
    links = get_link_repository()
    clock = get_clock()

    assert get_create_link_use_case(links, clock) is not get_create_link_use_case(links, clock)


def test_the_wired_use_cases_share_one_store() -> None:
    """
    Given a link created through the wired create use case,
    when the wired resolve and details use cases are asked about its code,
    then both find it -- which is the assertion that the three of them were handed the same
    repository, and that the implementations really satisfy the ports they are declared as.
    """
    links = get_link_repository()
    clicks = get_click_repository()
    clock = get_clock()

    created = get_create_link_use_case(links, clock).create(CreateLinkCommand(url=TARGET))
    redirect = get_resolve_link_use_case(links, clicks, clock).resolve(
        created.code, user_agent=None, referer=None, ip=None
    )
    details = get_link_details_use_case(links, clicks).get_details(created.code)

    assert created.was_created is True
    assert redirect.target_url == TARGET
    assert details.total_clicks == 1


def test_the_stamped_instant_comes_from_the_wired_clock() -> None:
    """
    Given the real clock behind the port,
    when a link is created through the wired use case,
    then its created_at is timezone aware, which is what the domain models refuse to exist without.
    """
    created = get_create_link_use_case(get_link_repository(), get_clock()).create(
        CreateLinkCommand(url=TARGET)
    )

    assert created.created_at.utcoffset() is not None
