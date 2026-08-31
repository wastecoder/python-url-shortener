"""The wiring, in one place: every port bound to an implementation, exactly once.

This is the only module that knows both a port and the thing that satisfies it. Controllers depend
on the `Annotated[...]` aliases below, which name **inbound ports** -- never an `...Impl` -- so no
controller can reach a use case implementation even by accident, and swapping one is an edit here
and nowhere else.

Every provider is annotated with the port it returns and not with the class it builds, and the
annotation is doing work rather than describing: it is what makes `mypy` verify that
`InMemoryLinkRepository` really satisfies `LinkRepository` and that `CreateLinkUseCaseImpl` really
satisfies `CreateLinkUseCase`. The ports are `Protocol`s, so nothing inherits from them and
structural conformance is only worth something where a type checker reads it. This file is where
it reads it, for production code -- `tests/fakes.py` does the same for the test doubles.

`@lru_cache` on the three driven ports makes them process-wide singletons, which is what an
in-memory store has to be: built per request, every request would get an empty database. The use
case providers are deliberately **not** cached -- they are three-line objects holding references,
and caching them would only hide which collaborators each one was given.

**In Fase 4 the repository swap is this file, plus deleting one module.** The two repository
providers stop returning the in-memory implementations and start returning the SQLAlchemy ones,
bound to a request-scoped session; `adapter/persistence/in_memory_repositories.py` goes away; and
the `@lru_cache` comes off those two, because it exists to make an in-memory store a process-wide
singleton and would otherwise hand one session to every request. **No controller, no DTO and no
handler moves for it**, and that is the demonstration the architecture is here to produce.

The claim is about the swap and not about the whole phase, and the difference matters because
`adapter/web/health_controller.py` *does* change in Fase 4 -- it stops answering a static `ok` and
starts running `SELECT 1`. That is a new endpoint behaviour arriving, not a repository leaking
upward, and it is written down in the Fase 4 section of `PROGRESS-V1.md` together with the test
that has to be rewritten with it.
"""

from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from url_shortener.adapter.config.clock import SystemClock
from url_shortener.adapter.config.settings import Settings, get_settings
from url_shortener.adapter.persistence.in_memory_repositories import (
    InMemoryClickRepository,
    InMemoryLinkRepository,
)
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


@lru_cache
def get_link_repository() -> LinkRepository:
    """The store of links. In-memory until Fase 4, and a process-wide singleton because of it."""
    return InMemoryLinkRepository()


@lru_cache
def get_click_repository() -> ClickRepository:
    """The store of clicks. In-memory until Fase 4, and a process-wide singleton because of it."""
    return InMemoryClickRepository()


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
