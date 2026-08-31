"""The in-memory repositories Fase 3 runs against, including what they do under threads."""

import threading
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from url_shortener.adapter.persistence.in_memory_repositories import (
    InMemoryClickRepository,
    InMemoryLinkRepository,
)
from url_shortener.domain.model.click import Click
from url_shortener.domain.model.link import Link
from url_shortener.domain.model.short_code import ShortCode
from url_shortener.domain.service.url_hash import hash_url

CREATED_AT = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)
TARGET = "https://example.com/a"
OTHER_TARGET = "https://example.com/b"

THREADS = 8
CONTESTED_URLS = tuple(f"https://example.com/contested/{index}" for index in range(20))

# A deadlock has to become a failure rather than a hang, so the threads are joined with a bound
# and are daemons -- otherwise a wrong lock here would freeze the whole suite instead of
# reporting itself.
JOIN_TIMEOUT_SECONDS = 30.0


def _link(link_id: int, url: str = TARGET) -> Link:
    return Link(id=link_id, code=ShortCode.from_id(link_id), url=url, created_at=CREATED_AT)


def _store(links: InMemoryLinkRepository, url: str = TARGET) -> Link:
    link = _link(links.next_id(), url)
    links.save(link, url_hash=hash_url(url))
    return link


def test_the_first_id_is_one_and_the_next_ones_follow() -> None:
    """
    Given a fresh store,
    when ids are taken from it,
    then they start at 1, because that is where a BIGSERIAL sequence starts.
    """
    links = InMemoryLinkRepository()

    assert [links.next_id() for _ in range(3)] == [1, 2, 3]


def test_an_empty_store_answers_nothing_to_both_lookups() -> None:
    """
    Given a fresh store,
    when it is asked for a code and for a digest,
    then both answer None rather than raising.
    """
    links = InMemoryLinkRepository()

    assert links.find_by_code(ShortCode.from_id(1)) is None
    assert links.find_by_url_hash(hash_url(TARGET)) is None


def test_a_saved_link_is_found_by_its_code_and_by_its_digest() -> None:
    """
    Given a link saved into the store,
    when it is looked up either way,
    then the same link comes back, because both dictionaries are written by one save.
    """
    links = InMemoryLinkRepository()
    link = _link(links.next_id())

    assert links.save(link, url_hash=hash_url(TARGET)) is True
    assert links.find_by_code(link.code) == link
    assert links.find_by_url_hash(hash_url(TARGET)) == link


def test_a_digest_that_is_already_taken_refuses_the_insert() -> None:
    """
    Given a URL that already has a link,
    when a second link is saved for the same digest,
    then the save answers False and the stored row is still the first one.
    """
    links = InMemoryLinkRepository()
    winner = _store(links)
    loser = _link(links.next_id())

    assert links.save(loser, url_hash=hash_url(TARGET)) is False
    assert links.find_by_url_hash(hash_url(TARGET)) == winner
    assert links.find_by_code(loser.code) is None


def test_a_different_url_gets_its_own_row() -> None:
    """
    Given a store holding one link,
    when a link for another URL is saved,
    then it is accepted, because the uniqueness rule is about the digest and not about links.
    """
    links = InMemoryLinkRepository()
    first = _store(links)
    second = _store(links, OTHER_TARGET)

    assert first != second
    assert links.find_by_url_hash(hash_url(OTHER_TARGET)) == second


def test_clicks_are_counted_per_link() -> None:
    """
    Given clicks recorded for two links,
    when each link's total is asked for,
    then each count covers only its own rows.
    """
    clicks = InMemoryClickRepository()
    for link_id in (1, 1, 2):
        clicks.record(Click(link_id=link_id, occurred_at=CREATED_AT))

    assert clicks.count_by_link(1) == 2
    assert clicks.count_by_link(2) == 1


def test_a_link_nobody_followed_counts_zero() -> None:
    """
    Given a store with no click for a link,
    when its total is asked for,
    then it is zero rather than missing, because the count is derived from rows.
    """
    assert InMemoryClickRepository().count_by_link(1) == 0


def test_concurrent_use_finishes_and_leaves_a_store_that_agrees_with_itself() -> None:
    """
    Given many threads taking ids, saving links for the same URLs and recording clicks at once,
    when each of them is joined with a bound,
    then every thread finished and the store is coherent: one row per URL, each reachable by its
    code, and one click per thread against the row that won.

    What this test can prove and what it cannot are different things, and the difference is the
    point. It cannot show the locks mattering: CPython's GIL was measured never to interleave the
    read-modify-write they guard, so removing them keeps this green. It does catch the mistakes a
    lock actually causes -- taking a non-reentrant lock twice, which hangs, and guarding one half
    of an invariant, which leaves the two dictionaries disagreeing.
    """
    links = InMemoryLinkRepository()
    clicks = InMemoryClickRepository()
    ready = threading.Barrier(THREADS)
    errors: list[Exception] = []
    collecting = threading.Lock()

    def contend() -> None:
        try:
            ready.wait()
            for url in CONTESTED_URLS:
                link = _link(links.next_id(), url)
                if not links.save(link, url_hash=hash_url(url)):
                    winner = links.find_by_url_hash(hash_url(url))
                    if winner is None:
                        raise AssertionError(f"the digest of {url} carried no row")
                    link = winner
                clicks.record(Click(link_id=link.id, occurred_at=CREATED_AT))
        except Exception as failure:
            with collecting:
                errors.append(failure)

    threads = [threading.Thread(target=contend, daemon=True) for _ in range(THREADS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(JOIN_TIMEOUT_SECONDS)

    assert [thread for thread in threads if thread.is_alive()] == []
    assert errors == []
    for url in CONTESTED_URLS:
        stored = links.find_by_url_hash(hash_url(url))
        assert stored is not None
        assert links.find_by_code(stored.code) == stored
        assert clicks.count_by_link(stored.id) == THREADS


if TYPE_CHECKING:
    # The conformance proof, in the same shape `tests/fakes.py` uses: assignments that never run,
    # so that a repository drifting away from its port fails `uv run mypy` with the conflicting
    # member and both signatures printed. `adapter/config/dependencies.py` proves the same thing
    # a second time, from production code, by annotating each provider with the port it returns.
    from url_shortener.application.port.outbound.click_repository import ClickRepository
    from url_shortener.application.port.outbound.link_repository import LinkRepository

    _links: LinkRepository = InMemoryLinkRepository()
    _clicks: ClickRepository = InMemoryClickRepository()
