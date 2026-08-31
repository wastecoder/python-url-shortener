"""Following a short code: where it sends the caller, and the click that gets written."""

from datetime import UTC, datetime
from ipaddress import ip_address

import pytest

from tests.fakes import FixedClock, InMemoryClickRepository, InMemoryLinkRepository
from tests.mothers import LinkMother, TargetUrlMother
from url_shortener.application.port.inbound.resolve_link_use_case import ResolveLinkUseCase
from url_shortener.application.usecase.resolve_link_use_case import ResolveLinkUseCaseImpl
from url_shortener.domain.exception.link_not_found_error import LinkNotFoundError
from url_shortener.domain.model.link import Link
from url_shortener.domain.model.short_code import ShortCode
from url_shortener.domain.service.url_hash import hash_url

# Two instants, on purpose. The stored link is stamped by the mother, at `mothers.CREATED_AT`;
# the clock reports this one. With a single instant feeding both, a click stamped with the moment
# the *link* was created would compare equal to a click stamped with the moment it was *followed*,
# and the assertion below would prove nothing.
VISITED_AT = datetime(2026, 9, 2, 9, 30, 15, 123456, tzinfo=UTC)
TARGET = TargetUrlMother.accepted()


def _use_case(links: InMemoryLinkRepository, clicks: InMemoryClickRepository) -> ResolveLinkUseCase:
    """Build the subject, annotated with the port: the return type is the conformance assertion."""
    return ResolveLinkUseCaseImpl(links, clicks, FixedClock(VISITED_AT))


def _store_one_link(links: InMemoryLinkRepository, url: str = TARGET) -> Link:
    """Put one link in the store the way the use case would find it, and hand it back."""
    link = LinkMother.with_id(links.next_id(), url=url)
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
    assert click.occurred_at == VISITED_AT
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


def test_the_click_is_billed_to_the_link_that_was_followed() -> None:
    """
    Given two stored links,
    when the second one is followed,
    then the click points at the second and the first is still untouched. Every link in a fresh
    store would otherwise be id 1, and an assertion about the id would only be asserting that.
    """
    links = InMemoryLinkRepository()
    clicks = InMemoryClickRepository()
    first = _store_one_link(links)
    second = _store_one_link(links, "https://example.com/b")

    _use_case(links, clicks).resolve(str(second.code), user_agent=None, referer=None, ip=None)

    assert clicks.recorded[0].link_id == second.id
    assert clicks.count_by_link(first.id) == 0


def test_the_destination_comes_back_byte_for_byte() -> None:
    """
    Given a link stored with mixed case in its path and a trailing slash,
    when its code is resolved,
    then the destination is the string that was stored, untouched: a redirect that tidied the URL
    would send the caller somewhere the owner never asked for.
    """
    links = InMemoryLinkRepository()
    exact = "https://example.com/AbC/"
    link = _store_one_link(links, exact)

    result = _use_case(links, InMemoryClickRepository()).resolve(
        str(link.code), user_agent=None, referer=None, ip=None
    )

    assert result.target_url == exact


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
