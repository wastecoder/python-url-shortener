"""Reading a link: its destination, its age, and how often it has been followed."""

from datetime import UTC, datetime

import pytest

from tests.fakes import InMemoryClickRepository, InMemoryLinkRepository
from url_shortener.application.port.inbound.get_link_details_use_case import GetLinkDetailsUseCase
from url_shortener.application.usecase.get_link_details_use_case import GetLinkDetailsUseCaseImpl
from url_shortener.domain.exception.link_not_found_error import LinkNotFoundError
from url_shortener.domain.model.click import Click
from url_shortener.domain.model.link import Link
from url_shortener.domain.model.short_code import ShortCode
from url_shortener.domain.service.url_hash import hash_url

INSTANT = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)
TARGET = "https://example.com/a"


def _use_case(
    links: InMemoryLinkRepository, clicks: InMemoryClickRepository
) -> GetLinkDetailsUseCase:
    """Build the subject, annotated with the port: the return type is the conformance assertion."""
    return GetLinkDetailsUseCaseImpl(links, clicks)


def _store_one_link(links: InMemoryLinkRepository, url: str = TARGET) -> Link:
    link_id = links.next_id()
    link = Link(id=link_id, code=ShortCode.from_id(link_id), url=url, created_at=INSTANT)
    links.save(link, url_hash=hash_url(url))
    return link


def test_the_details_report_the_link_and_how_often_it_was_followed() -> None:
    """
    Given a stored link that has been followed twice,
    when its details are read,
    then the destination, the creation instant and the total come back together.
    """
    links = InMemoryLinkRepository()
    clicks = InMemoryClickRepository()
    link = _store_one_link(links)
    clicks.record(Click(link_id=link.id, occurred_at=INSTANT))
    clicks.record(Click(link_id=link.id, occurred_at=INSTANT))

    result = _use_case(links, clicks).get_details(str(link.code))

    assert result.code == str(link.code)
    assert result.url == TARGET
    assert result.created_at == INSTANT
    assert result.total_clicks == 2


def test_a_link_nobody_followed_reports_no_clicks() -> None:
    """
    Given a link that has never been followed,
    when its details are read,
    then the total is zero, because the total is a count and not a stored counter.
    """
    links = InMemoryLinkRepository()
    link = _store_one_link(links)

    result = _use_case(links, InMemoryClickRepository()).get_details(str(link.code))

    assert result.total_clicks == 0


def test_the_total_counts_this_link_and_no_other() -> None:
    """
    Given two links, each with its own accesses,
    when the details of the second are read,
    then only its own clicks are counted. The second and not the first on purpose: every link in
    a fresh store would be id 1, so reading the first would count the right number by accident.
    """
    links = InMemoryLinkRepository()
    clicks = InMemoryClickRepository()
    first = _store_one_link(links)
    second = _store_one_link(links, "https://example.com/b")
    clicks.record(Click(link_id=first.id, occurred_at=INSTANT))
    clicks.record(Click(link_id=second.id, occurred_at=INSTANT))
    clicks.record(Click(link_id=second.id, occurred_at=INSTANT))

    result = _use_case(links, clicks).get_details(str(second.code))

    assert result.total_clicks == 2


def test_the_destination_is_reported_byte_for_byte() -> None:
    """
    Given a link stored with mixed case in its path and a trailing slash,
    when its details are read,
    then the URL comes back exactly as stored: this endpoint is how a caller checks where a link
    points, so a tidied answer would be a wrong answer.
    """
    links = InMemoryLinkRepository()
    exact = "https://example.com/AbC/"
    link = _store_one_link(links, exact)

    result = _use_case(links, InMemoryClickRepository()).get_details(str(link.code))

    assert result.url == exact


def test_reading_the_details_records_nothing() -> None:
    """
    Given a stored link,
    when its details are read twice,
    then no click was appended: asking how often a link was followed is not following it, and if
    it counted, the number would be changed by the act of asking for it.
    """
    links = InMemoryLinkRepository()
    clicks = InMemoryClickRepository()
    link = _store_one_link(links)
    use_case = _use_case(links, clicks)

    use_case.get_details(str(link.code))
    use_case.get_details(str(link.code))

    assert clicks.recorded == ()


def test_an_unknown_code_is_not_found() -> None:
    """
    Given a well-formed code that belongs to no link,
    when its details are read,
    then LinkNotFoundError is raised, carrying the code that was asked for.
    """
    with pytest.raises(LinkNotFoundError) as caught:
        _use_case(InMemoryLinkRepository(), InMemoryClickRepository()).get_details("0000009")

    assert caught.value.code == "0000009"


@pytest.mark.parametrize("code", ["", "a", "links", "00000000", "000-000"])
def test_a_path_that_is_not_a_code_is_not_found_either(code: str) -> None:
    """
    Given a path segment that is not a short code at all,
    when its details are read,
    then the answer is the same LinkNotFoundError this route gives for an unknown code.
    """
    with pytest.raises(LinkNotFoundError) as caught:
        _use_case(InMemoryLinkRepository(), InMemoryClickRepository()).get_details(code)

    assert caught.value.code == code
