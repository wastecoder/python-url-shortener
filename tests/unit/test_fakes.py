"""The in-memory doubles behave like the tables they stand for.

Every use case assertion in this phase rests on these four methods, and `mypy` proves their shape
and explicitly not their behaviour -- a `save` that stored nothing and returned `True` would type
check perfectly. In Fase 5 this file is the seed of a contract suite run against both the fake and
the real repository, at which point it stops testing a double and starts specifying both.
"""

from datetime import UTC, datetime
from ipaddress import ip_address

import pytest

from tests.fakes import FixedClock, InMemoryClickRepository, InMemoryLinkRepository
from url_shortener.domain.model.click import Click
from url_shortener.domain.model.link import Link
from url_shortener.domain.model.short_code import ShortCode
from url_shortener.domain.service.url_hash import hash_url

INSTANT = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)


def _link(link_id: int, url: str) -> Link:
    return Link(id=link_id, code=ShortCode.from_id(link_id), url=url, created_at=INSTANT)


def test_the_sequence_hands_out_increasing_ids_and_remembers_what_it_spent() -> None:
    """
    Given a fresh store,
    when three ids are taken,
    then they increase from one and every value taken is visible, spent or not.
    """
    links = InMemoryLinkRepository()

    taken = [links.next_id(), links.next_id(), links.next_id()]

    assert taken == [1, 2, 3]
    assert links.issued_ids == [1, 2, 3]


def test_a_saved_link_is_found_by_its_code_and_by_its_digest() -> None:
    """
    Given a link saved with the digest of its URL,
    when it is looked up either way,
    then both lookups return it, because both are unique indexes on the same row.
    """
    links = InMemoryLinkRepository()
    link = _link(1, "https://example.com")
    url_hash = hash_url(link.url)

    assert links.save(link, url_hash=url_hash) is True
    assert links.find_by_code(link.code) is link
    assert links.find_by_url_hash(url_hash) is link


def test_an_unknown_code_and_an_unknown_digest_are_both_absent() -> None:
    """
    Given a store holding one link,
    when a code and a digest that belong to no row are looked up,
    then both answer None rather than raising, which is what the port promises.
    """
    links = InMemoryLinkRepository()
    links.save(_link(1, "https://example.com"), url_hash=hash_url("https://example.com"))

    assert links.find_by_code(ShortCode.from_id(999)) is None
    assert links.find_by_url_hash(hash_url("https://other.example")) is None


def test_the_second_save_of_one_digest_is_refused_and_changes_nothing() -> None:
    """
    Given a link already saved under a digest,
    when a different link is saved under that same digest,
    then the insert is refused and the stored row is still the first one.
    """
    links = InMemoryLinkRepository()
    url_hash = hash_url("https://example.com")
    first = _link(1, "https://example.com")
    links.save(first, url_hash=url_hash)

    assert links.save(_link(2, "https://example.com"), url_hash=url_hash) is False
    assert links.rows == (first,)


def test_a_rival_committed_in_the_race_window_makes_the_next_save_lose() -> None:
    """
    Given a rival arranged to commit the same digest inside the race window,
    when a link is saved under that digest,
    then the save is refused and the rival is the row that survived.
    """
    links = InMemoryLinkRepository()
    url_hash = hash_url("https://example.com")
    rival = _link(1, "https://example.com")
    links.insert_before_next_save(rival, url_hash=url_hash)

    assert links.save(_link(2, "https://example.com"), url_hash=url_hash) is False
    assert links.rows == (rival,)


def test_the_arranged_rival_commits_once_and_not_on_every_save() -> None:
    """
    Given a rival arranged once,
    when a second, unrelated link is saved afterwards,
    then that save succeeds: a race is a moment, not a condition the store stays in.
    """
    links = InMemoryLinkRepository()
    rival = _link(1, "https://example.com")
    links.insert_before_next_save(rival, url_hash=hash_url("https://example.com"))
    links.save(_link(2, "https://example.com"), url_hash=hash_url("https://example.com"))

    other = _link(3, "https://other.example")

    assert links.save(other, url_hash=hash_url("https://other.example")) is True
    assert links.rows == (rival, other)


def test_the_stored_rows_are_a_tuple_a_test_cannot_edit() -> None:
    """
    Given a store holding a link,
    when its rows are read,
    then they come back as a tuple, so an assertion cannot quietly mutate the store it inspects.
    """
    links = InMemoryLinkRepository()
    links.save(_link(1, "https://example.com"), url_hash=hash_url("https://example.com"))
    clicks = InMemoryClickRepository()
    clicks.record(Click(link_id=1, occurred_at=INSTANT))

    assert isinstance(links.rows, tuple)
    assert isinstance(clicks.recorded, tuple)


def test_clicks_are_appended_in_order_and_never_replaced() -> None:
    """
    Given three accesses to the same link,
    when they are recorded,
    then all three are kept, in the order they arrived.
    """
    clicks = InMemoryClickRepository()
    recorded = [
        Click(link_id=1, occurred_at=INSTANT, user_agent="curl"),
        Click(link_id=1, occurred_at=INSTANT, referer="https://example.com"),
        Click(link_id=1, occurred_at=INSTANT, ip=ip_address("8.8.8.8")),
    ]
    for click in recorded:
        clicks.record(click)

    assert clicks.recorded == tuple(recorded)


def test_the_count_belongs_to_one_link_and_not_to_the_table() -> None:
    """
    Given clicks recorded against two different links,
    when each link is counted,
    then each answer counts only its own, and a link nobody followed counts zero.
    """
    clicks = InMemoryClickRepository()
    clicks.record(Click(link_id=1, occurred_at=INSTANT))
    clicks.record(Click(link_id=1, occurred_at=INSTANT))
    clicks.record(Click(link_id=2, occurred_at=INSTANT))

    assert clicks.count_by_link(1) == 2
    assert clicks.count_by_link(2) == 1
    assert clicks.count_by_link(3) == 0


def test_a_fixed_clock_answers_the_same_instant_every_time() -> None:
    """
    Given a clock built at one instant,
    when it is asked twice,
    then both answers are that instant, which is what makes a written timestamp assertable.
    """
    clock = FixedClock(INSTANT)

    assert clock.now() == INSTANT
    assert clock.now() == INSTANT


def test_a_fixed_clock_refuses_a_naive_instant() -> None:
    """
    Given an instant with no offset from UTC,
    when a clock is built from it,
    then construction fails here, rather than three frames later inside a domain model.
    """
    with pytest.raises(ValueError, match="aware instant"):
        FixedClock(datetime(2026, 8, 31, 12, 0))
