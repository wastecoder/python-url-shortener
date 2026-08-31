"""The wiring, in one place: every port bound to an implementation, exactly once.

This is the only module that knows both a port and the thing that satisfies it. Controllers depend
on the `Annotated[...]` aliases below, which name **inbound ports** -- never an `...Impl` -- so no
controller can reach a use case implementation even by accident, and swapping one is an edit here
and nowhere else.

Every provider is annotated with the port it returns and not with the class it builds, and the
annotation is doing work rather than describing: it is what makes `mypy` verify that
`LinkRepositoryImpl` really satisfies `LinkRepository` and that `CreateLinkUseCaseImpl` really
satisfies `CreateLinkUseCase`. The ports are `Protocol`s, so nothing inherits from them and
structural conformance is only worth something where a type checker reads it. This file is where it
reads it, for production code -- `tests/fakes.py` does the same for the test doubles.

**The transaction boundary is `get_session`, and it is the subject of ADR-0007.** One session per
request, shared by both repositories through FastAPI's sub-dependency cache, so the `SELECT` of a
link and the `INSERT` of its click are genuinely one transaction. The `scope="function"` is the
whole decision in one word: without it the session's exit code runs *after* the response has been
sent, and a `COMMIT` that fails then has no response left to change -- the caller would already
hold a `302` for a redirect that recorded nothing.

`@lru_cache` survives on `get_clock` alone. A clock has no state, so one is as good as many. It
came off the two repositories when they stopped being dictionaries: cached, they would hand a
single request-scoped session to every request for the life of the process.
"""

from collections.abc import Iterator
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session, sessionmaker

from url_shortener.adapter.config.clock import SystemClock
from url_shortener.adapter.config.settings import Settings, get_settings
from url_shortener.adapter.persistence.click_repository_impl import ClickRepositoryImpl
from url_shortener.adapter.persistence.link_repository_impl import LinkRepositoryImpl
from url_shortener.application.port.inbound.create_link_use_case import CreateLinkUseCase
from url_shortener.application.port.inbound.get_link_details_use_case import GetLinkDetailsUseCase
from url_shortener.application.port.inbound.resolve_link_use_case import ResolveLinkUseCase
from url_shortener.application.port.outbound.click_repository import ClickRepository
from url_shortener.application.port.outbound.clock import Clock
from url_shortener.application.port.outbound.link_repository import LinkRepository
from url_shortener.application.usecase.create_link_use_case import CreateLinkUseCaseImpl
from url_shortener.application.usecase.get_link_details_use_case import GetLinkDetailsUseCaseImpl
from url_shortener.application.usecase.resolve_link_use_case import ResolveLinkUseCaseImpl


@lru_cache
def get_clock() -> Clock:
    """The clock every use case stamps its timestamps from."""
    return SystemClock()


def get_session(request: Request) -> Iterator[Session]:
    """One session, one transaction, for the duration of one request. ADR-0007.

    The factory comes off `app.state`, where the lifespan put it, rather than from a module-level
    singleton: an engine built at import time is a connection pool created as a side effect of an
    `import`, which nothing can then opt out of.

    `sessionmaker.begin()` rather than a hand-written `commit()` in a `try` -- a clean exit commits,
    an exception rolls back, and both live in SQLAlchemy's own context manager instead of in four
    lines somebody has to re-read to check.

    The `scope="function"` is on the alias below, and it is what makes this run while there is still
    a response to change. It is deliberately not the default.
    """
    factory: sessionmaker[Session] = request.app.state.session_factory
    with factory.begin() as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session, scope="function")]


def get_link_repository(session: SessionDep) -> LinkRepository:
    """The store of links, reading and writing inside this request's transaction."""
    return LinkRepositoryImpl(session)


def get_click_repository(session: SessionDep) -> ClickRepository:
    """The store of clicks, reading and writing inside this request's transaction.

    It is a second object over the *same* session, not a second session: FastAPI resolves
    `SessionDep` once per request and hands the result to every dependency that asks for it.
    """
    return ClickRepositoryImpl(session)


ClockDep = Annotated[Clock, Depends(get_clock)]
LinkRepositoryDep = Annotated[LinkRepository, Depends(get_link_repository)]
ClickRepositoryDep = Annotated[ClickRepository, Depends(get_click_repository)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_create_link_use_case(links: LinkRepositoryDep, clock: ClockDep) -> CreateLinkUseCase:
    """Shortening a URL needs somewhere to write links and something to stamp them with."""
    return CreateLinkUseCaseImpl(links, clock)


def get_resolve_link_use_case(
    links: LinkRepositoryDep, clicks: ClickRepositoryDep, clock: ClockDep
) -> ResolveLinkUseCase:
    """Following a code reads a link and appends a click, so it needs all three ports."""
    return ResolveLinkUseCaseImpl(links, clicks, clock)


def get_link_details_use_case(
    links: LinkRepositoryDep, clicks: ClickRepositoryDep
) -> GetLinkDetailsUseCase:
    """Reading details takes no clock: this use case only reads, so it has nothing to stamp."""
    return GetLinkDetailsUseCaseImpl(links, clicks)


CreateLinkUseCaseDep = Annotated[CreateLinkUseCase, Depends(get_create_link_use_case)]
ResolveLinkUseCaseDep = Annotated[ResolveLinkUseCase, Depends(get_resolve_link_use_case)]
GetLinkDetailsUseCaseDep = Annotated[GetLinkDetailsUseCase, Depends(get_link_details_use_case)]
