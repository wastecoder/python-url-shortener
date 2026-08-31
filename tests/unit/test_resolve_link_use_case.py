"""Following a short code: where it sends the caller, and the click that gets written."""

from datetime import UTC, datetime
from ipaddress import ip_address

import pytest

from tests.fakes import FixedClock, InMemoryClickRepository, InMemoryLinkRepository
from url_shortener.application.port.inbound.resolve_link_use_case import ResolveLinkUseCase
from url_shortener.application.usecase.resolve_link_use_case import ResolveLinkUseCaseImpl
from url_shortener.domain.exception.link_not_found_error import LinkNotFoundError
from url_shortener.domain.model.link import Link
from url_shortener.domain.model.short_code import ShortCode
from url_shortener.domain.service.url_hash import hash_url

INSTANT = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)
TARGET = "https://example.com/a"


def _use_case(links: InMemoryLinkRepository, clicks: InMemoryClickRepository) -> ResolveLinkUseCase:
    """Build the subject, annotated with the port: the return type is the conformance assertion."""
    return ResolveLinkUseCaseImpl(links, clicks, FixedClock(INSTANT))


def _store_one_link(links: InMemoryLinkRepository, url: str = TARGET) -> Link:
    link_id = links.next_id()
    link = Link(id=link_id, code=ShortCode.from_id(link_id), url=url, created_at=INSTANT)
    links.save(link, url_hash=hash_url(url))
    return link


class _RepositoryThatMustNotBeAsked(InMemoryLinkRepository):
    """A store that fails if it is queried at all, so "no round trip" becomes an assertion."""

    def find_by_code(self, code: ShortCode) -> Link | None:
        raise AssertionError(f"the repository was asked for {code!r}")


def test_a_known_code_answers_with_the_url_it_points_at() -> None:
    """
    Given a stored link,
    when its code is resolved,
    then the destination comes back, and it is the URL exactly as it was submitted.
    """
    links = InMemoryLinkRepository()
    link = _store_one_link(links)

    result = _use_case(links, InMemoryClickRepository()).resolve(
        str(link.code), user_agent=None, referer=None, ip=None
    )

    assert result.target_url == TARGET


def test_following_a_link_records_one_click_carrying_the_request_context() -> None:
    """
    Given a stored link and a request that offered a user agent, a referer and an address,
    when the code is resolved,
    then exactly one click is appended, pointing at that link, stamped by the clock, with each
    fact on its own field.
    """
    links = InMemoryLinkRepository()
    clicks = InMemoryClickRepository()
    link = _store_one_link(links)

    _use_case(links, clicks).resolve(
        str(link.code),
        user_agent="curl/8.5.0",
        referer="https://news.example",
        ip=ip_address("8.8.8.8"),
    )

    assert len(clicks.recorded) == 1
    click = clicks.recorded[0]
    assert click.link_id == link.id
    assert click.occurred_at == INSTANT
    assert click.user_agent == "curl/8.5.0"
    assert click.referer == "https://news.example"
    assert click.ip == ip_address("8.8.8.8")


def test_a_request_that_offered_no_context_still_records_the_click() -> None:
    """
    Given a request carrying none of the optional facts,
    when the code is resolved,
    then the click is still written, with those fields empty: an HTTP client owes none of them.
    """
    links = InMemoryLinkRepository()
    clicks = InMemoryClickRepository()
    link = _store_one_link(links)

    _use_case(links, clicks).resolve(str(link.code), user_agent=None, referer=None, ip=None)

    click = clicks.recorded[0]
    assert (click.user_agent, click.referer, click.ip) == (None, None, None)


def test_two_visits_to_one_link_append_two_clicks() -> None:
    """
    Given a link followed twice,
    when the clicks are counted,
    then both are there: the table is append-only, so a second visit adds rather than replaces.
    """
    links = InMemoryLinkRepository()
    clicks = InMemoryClickRepository()
    link = _store_one_link(links)
    use_case = _use_case(links, clicks)

    use_case.resolve(str(link.code), user_agent=None, referer=None, ip=None)
    use_case.resolve(str(link.code), user_agent=None, referer=None, ip=None)

    assert clicks.count_by_link(link.id) == 2


def test_an_unknown_code_is_not_found() -> None:
    """
    Given a well-formed code that belongs to no link,
    when it is resolved,
    then LinkNotFoundError is raised, carrying the code that was asked for.
    """
    links = InMemoryLinkRepository()

    with pytest.raises(LinkNotFoundError) as caught:
        _use_case(links, InMemoryClickRepository()).resolve(
            "0000009", user_agent=None, referer=None, ip=None
        )

    assert caught.value.code == "0000009"


@pytest.mark.parametrize(
    "code", ["", "a", "favicon.ico", "robots.txt", "00000000", "000-000", "0000 00"]
)
def test_a_path_that_is_not_a_code_is_not_found_either(code: str) -> None:
    """
    Given a path segment that is not a short code at all,
    when it is resolved,
    then the answer is the same LinkNotFoundError: this route is a catch-all at the root, so any
    path in the world reaches it and has to be answered rather than crashed on.
    """
    links = InMemoryLinkRepository()

    with pytest.raises(LinkNotFoundError) as caught:
        _use_case(links, InMemoryClickRepository()).resolve(
            code, user_agent=None, referer=None, ip=None
        )

    assert caught.value.code == code


def test_a_path_that_is_not_a_code_never_reaches_the_repository() -> None:
    """
    Given a store that fails if it is queried,
    when a path that cannot be a code is resolved,
    then the refusal came from parsing and not from a lookup: scanner traffic against the
    catch-all route costs no database round trip.
    """
    links = _RepositoryThatMustNotBeAsked()

    with pytest.raises(LinkNotFoundError):
        _use_case(links, InMemoryClickRepository()).resolve(
            "favicon.ico", user_agent=None, referer=None, ip=None
        )


def test_an_unknown_code_records_no_click() -> None:
    """
    Given a code that resolves to nothing,
    when it is resolved,
    then no click was appended: the lookup runs first, so a miss writes nothing at all.
    """
    clicks = InMemoryClickRepository()

    with pytest.raises(LinkNotFoundError):
        _use_case(InMemoryLinkRepository(), clicks).resolve(
            "0000009", user_agent="curl/8.5.0", referer=None, ip=None
        )

    assert clicks.recorded == ()
