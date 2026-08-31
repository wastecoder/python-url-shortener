"""The wiring: what is shared, what is rebuilt, and that the pieces really fit together.

Half of this file reads the dependency graph FastAPI built rather than calling anything, and that
is on purpose: since Fase 4 the two facts that matter most about the wiring -- one session per
request, closed before the response is sent -- are properties of the graph and not of any return
value. Neither can be observed by calling a provider, and only one of them can be observed at all
without a database.
"""

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute
from sqlalchemy.orm import Session

from tests.fakes import InMemoryClickRepository, InMemoryLinkRepository
from url_shortener.adapter.config.dependencies import (
    get_click_repository,
    get_clock,
    get_create_link_use_case,
    get_link_details_use_case,
    get_link_repository,
    get_resolve_link_use_case,
    get_session,
)
from url_shortener.adapter.persistence.database.session import (
    create_database_engine,
    create_session_factory,
)
from url_shortener.application.viewmodel.create_link_command import CreateLinkCommand

TARGET = "https://example.com/wiring"
UNREACHABLE = "postgresql+psycopg://nobody:nothing@203.0.113.7:5432/nowhere"


@pytest.fixture(autouse=True)
def unshared_clock() -> Iterator[None]:
    """Drop the cached clock around every test in this file.

    `get_clock` is the only provider still carrying `@lru_cache`, and the cache is process-wide, so
    a test that pinned one clock would leak it into whatever runs next. The two repository
    providers lost their cache when they stopped being dictionaries -- cached, they would hand one
    request's session to every later request.
    """
    get_clock.cache_clear()
    yield
    get_clock.cache_clear()


@pytest.fixture
def session() -> Iterator[Session]:
    """A real session over an engine pointed at nothing. It never connects."""
    factory = create_session_factory(create_database_engine(UNREACHABLE))
    with factory() as opened:
        yield opened


def _dependants(dependant: Dependant) -> Iterator[Dependant]:
    """Every node of a route's dependency tree, the root excluded."""
    for sub in dependant.dependencies:
        yield sub
        yield from _dependants(sub)


def _routes(app: FastAPI) -> Iterator[APIRoute]:
    """Every API route of the application, across the included routers."""
    for route in app.routes:
        original = getattr(route, "original_router", None)
        for candidate in original.routes if original is not None else [route]:
            if isinstance(candidate, APIRoute):
                yield candidate


def test_the_session_is_closed_before_the_response_is_sent(app: FastAPI) -> None:
    """
    Given every route that touches the database,
    when the session dependency is found in each route's dependency tree,
    then it declares scope "function".

    This is the assertion ADR-0007 exists for, and it is worth stating what it does and does not
    prove. It does not prove the ordering -- that was measured, and only an integration test that
    poisons the commit can re-measure it. What it proves is that the word is still there: the
    default scope is "request", the code without it is one token shorter and looks identical, and
    under it a failed COMMIT leaves the caller holding a 302 for a redirect that recorded nothing.
    """
    found = [
        node
        for route in _routes(app)
        for node in _dependants(route.dependant)
        if node.call is get_session
    ]

    assert found, "no route reaches the database at all"
    assert {node.scope for node in found} == {"function"}


def test_both_repositories_read_one_session_per_request(app: FastAPI) -> None:
    """
    Given the redirect route, which reads a link and writes a click,
    when its dependency tree is read,
    then both repositories depend on the session and every one of those edges is cached -- which is
    what makes FastAPI resolve it once and hand the same session to both, so the read and the write
    of one redirect are one transaction rather than two.
    """
    redirect = next(route for route in _routes(app) if route.path == "/{code}")
    repositories = [
        node
        for node in _dependants(redirect.dependant)
        if node.call in (get_link_repository, get_click_repository)
    ]

    assert len(repositories) == 2
    for repository in repositories:
        sessions = [node for node in repository.dependencies if node.call is get_session]
        assert len(sessions) == 1
        assert sessions[0].use_cache is True


def test_the_health_route_is_kept_out_of_the_request_transaction(app: FastAPI) -> None:
    """
    Given the health route,
    when its dependency tree is read,
    then the session is not in it. A /health enlisted in the request transaction would fail when
    the pool is exhausted -- a reason that has nothing to do with the health it reports.
    """
    health = next(route for route in _routes(app) if route.path == "/health")

    assert not [node for node in _dependants(health.dependant) if node.call is get_session]


def test_the_clock_is_shared_and_the_repositories_are_not(session: Session) -> None:
    """
    Given the driven port providers,
    when each is asked twice,
    then the clock is the same object and each repository is a new one -- a stateless clock can be
    a process-wide singleton, and a repository holding a request-scoped session must not be.
    """
    assert get_clock() is get_clock()
    assert get_link_repository(session) is not get_link_repository(session)
    assert get_click_repository(session) is not get_click_repository(session)


def test_each_use_case_is_built_fresh() -> None:
    """
    Given the use case providers,
    when one is asked twice,
    then two objects come back: they hold references and nothing else, so caching them would only
    hide which collaborators each was handed.
    """
    links = InMemoryLinkRepository()
    clock = get_clock()

    assert get_create_link_use_case(links, clock) is not get_create_link_use_case(links, clock)


def test_the_wired_use_cases_share_one_store() -> None:
    """
    Given a link created through the wired create use case,
    when the wired resolve and details use cases are asked about its code,
    then both find it -- the assertion that the three of them were handed the same repository.

    The stores are the test fakes rather than the real repositories, and that is the whole reason
    this test survived the swap: the providers take their collaborators as parameters, so what is
    under test here is the wiring, and the wiring is the same object graph whether the store behind
    it is a dictionary or PostgreSQL. Proving the same thing against PostgreSQL is Fase 5's job.
    """
    links = InMemoryLinkRepository()
    clicks = InMemoryClickRepository()
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
    created = get_create_link_use_case(InMemoryLinkRepository(), get_clock()).create(
        CreateLinkCommand(url=TARGET)
    )

    assert created.created_at.utcoffset() is not None
