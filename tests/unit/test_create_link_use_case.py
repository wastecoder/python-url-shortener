"""Creating a link: the order of the steps, and what happens when two requests collide."""

from datetime import UTC, datetime

import pytest

from tests.fakes import FixedClock, InMemoryLinkRepository
from url_shortener.application.port.inbound.create_link_use_case import CreateLinkUseCase
from url_shortener.application.usecase.create_link_use_case import CreateLinkUseCaseImpl
from url_shortener.application.viewmodel.create_link_command import CreateLinkCommand
from url_shortener.domain.exception.domain_error import DomainError
from url_shortener.domain.exception.invalid_target_url_error import InvalidTargetUrlError
from url_shortener.domain.model.link import Link
from url_shortener.domain.model.short_code import ShortCode
from url_shortener.domain.service.url_hash import UrlHash, hash_url

INSTANT = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)
TARGET = "https://example.com/a"


def _use_case(links: InMemoryLinkRepository) -> CreateLinkUseCase:
    """Build the subject, annotated with the port: the return type is the conformance assertion."""
    return CreateLinkUseCaseImpl(links, FixedClock(INSTANT))


class _RepositoryThatRefusesWithoutStoring(InMemoryLinkRepository):
    """A store that contradicts itself: the insert conflicts and no row carries the digest.

    Nothing real behaves this way -- which is the point. It exists to reach the one branch the
    in-memory store cannot produce, and it lives here rather than in `tests/fakes.py` so that the
    fakes stay a model of the database instead of a museum of impossible states.
    """

    def save(self, link: Link, *, url_hash: UrlHash) -> bool:
        return False


def test_a_new_url_becomes_the_link_whose_code_is_its_id_in_base_62() -> None:
    """
    Given a store with nothing in it,
    when a URL is shortened,
    then a link is created whose code is the first sequence value in base 62, and the answer says
    it was created.
    """
    links = InMemoryLinkRepository()

    result = _use_case(links).create(CreateLinkCommand(TARGET))

    assert result.code == "0000001"
    assert result.url == TARGET
    assert result.created_at == INSTANT
    assert result.was_created is True
    assert links.rows == (Link(id=1, code=ShortCode("0000001"), url=TARGET, created_at=INSTANT),)


def test_the_stored_link_is_found_by_the_digest_of_the_url_it_points_at() -> None:
    """
    Given a URL that was just shortened,
    when the store is searched by the digest of that URL,
    then the link is there, which is the index the deduplication of the next request rides on.
    """
    links = InMemoryLinkRepository()

    _use_case(links).create(CreateLinkCommand(TARGET))

    assert links.find_by_url_hash(hash_url(TARGET)) is not None


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com",
        "javascript:alert(1)",
        "http://localhost/a",
        "http://127.0.0.1/a",
        "http://user:secret@example.com",
        "not a url at all",
    ],
)
def test_a_refused_url_produces_no_effect_at_all(url: str) -> None:
    """
    Given a URL the domain policy refuses,
    when it is shortened,
    then the refusal arrives and nothing was spent: no sequence value taken, no row written.
    """
    links = InMemoryLinkRepository()

    with pytest.raises(InvalidTargetUrlError):
        _use_case(links).create(CreateLinkCommand(url))

    assert links.issued_ids == []
    assert links.rows == ()


def test_the_same_url_twice_returns_the_same_link_and_creates_one_row() -> None:
    """
    Given a URL that already has a link,
    when the same URL is shortened again,
    then the existing link comes back, marked as not created, and no second row exists.
    """
    links = InMemoryLinkRepository()
    use_case = _use_case(links)
    first = use_case.create(CreateLinkCommand(TARGET))

    second = use_case.create(CreateLinkCommand(TARGET))

    assert second.code == first.code
    assert second.was_created is False
    assert len(links.rows) == 1


def test_the_deduplication_fast_path_spends_no_sequence_value() -> None:
    """
    Given a URL that already has a link,
    when the same URL is shortened again,
    then no new id was taken: the lookup by digest answers before the sequence is touched.
    """
    links = InMemoryLinkRepository()
    use_case = _use_case(links)
    use_case.create(CreateLinkCommand(TARGET))

    use_case.create(CreateLinkCommand(TARGET))

    assert links.issued_ids == [1]


def test_two_different_urls_get_two_different_codes() -> None:
    """
    Given two distinct URLs,
    when both are shortened,
    then each gets its own code, because each took its own sequence value.
    """
    links = InMemoryLinkRepository()
    use_case = _use_case(links)

    first = use_case.create(CreateLinkCommand(TARGET))
    second = use_case.create(CreateLinkCommand("https://example.com/b"))

    assert (first.code, second.code) == ("0000001", "0000002")


def test_losing_the_insert_race_answers_with_the_link_that_won() -> None:
    """
    Given another request that commits the same URL inside the race window,
    when this request tries to insert,
    then the answer is the winner's link and not the one this request built and threw away.
    """
    links = InMemoryLinkRepository()
    rival_id = links.next_id()
    rival = Link(id=rival_id, code=ShortCode.from_id(rival_id), url=TARGET, created_at=INSTANT)
    links.insert_before_next_save(rival, url_hash=hash_url(TARGET))

    result = _use_case(links).create(CreateLinkCommand(TARGET))

    assert result.code == "0000001"
    assert result.was_created is False
    assert links.rows == (rival,)


def test_losing_the_race_leaves_the_spent_sequence_value_as_a_gap() -> None:
    """
    Given a request that lost the insert race,
    when the ids taken from the sequence are read,
    then the value it spent is gone for good: a gap is expected, because the sequence generates
    ids and does not count links.
    """
    links = InMemoryLinkRepository()
    rival_id = links.next_id()
    links.insert_before_next_save(
        Link(id=rival_id, code=ShortCode.from_id(rival_id), url=TARGET, created_at=INSTANT),
        url_hash=hash_url(TARGET),
    )

    _use_case(links).create(CreateLinkCommand(TARGET))

    assert links.issued_ids == [1, 2]
    assert [link.id for link in links.rows] == [1]


def test_a_store_that_refuses_without_storing_is_an_internal_error() -> None:
    """
    Given a store whose insert conflicts while no row carries the digest,
    when a URL is shortened,
    then the failure is a RuntimeError and explicitly not a DomainError: no caller caused this
    and no caller can fix it, so it belongs on the 500 row and not in the error taxonomy.
    """
    links = _RepositoryThatRefusesWithoutStoring()

    with pytest.raises(RuntimeError) as caught:
        _use_case(links).create(CreateLinkCommand(TARGET))

    assert not isinstance(caught.value, DomainError)
