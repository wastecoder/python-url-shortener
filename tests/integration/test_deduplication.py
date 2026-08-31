"""Deduplication, and the race it has to survive: the argument this whole project is built around.

Three levels of proof, deliberately, because none of them is enough alone.

1. **Sequentially** -- the same URL twice comes back as one link. True of any correct
   implementation, including a check-then-insert that is broken under load.
2. **Deterministically** -- the four-step flow with another writer committed by hand inside the
   race window. This is the only one that always exercises the losing branch, and it is the only
   one that cannot be lucky.
3. **Concurrently** -- eight simultaneous requests through HTTP. This is the one that cannot be
   written with a mock at all, because what is under test is PostgreSQL's behaviour and not a
   return value.
"""

import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from http import HTTPStatus
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from tests.mothers import LinkMother, TargetUrlMother
from url_shortener.adapter.persistence.database.session import (
    create_database_engine,
    create_session_factory,
)
from url_shortener.adapter.persistence.link_repository_impl import LinkRepositoryImpl
from url_shortener.domain.service.url_hash import hash_url

pytestmark = pytest.mark.integration

# Eight, and the number is bounded from both sides. The engine's pool is five connections plus ten
# of overflow, so anything past fifteen would stop measuring the database and start measuring
# `pool_timeout`; and fewer than a handful is a race too small to be worth calling one.
RACERS = 8


def _count(database: Engine, table: str) -> int:
    """How many rows that table holds, read from outside the application's transaction."""
    with database.connect() as connection:
        return int(connection.execute(text(f"SELECT count(*) FROM {table}")).scalar_one())


def _ids_spent(database: Engine) -> int:
    """How many values the id sequence has handed out since the last truncation.

    `last_value` alone answers this only because `TRUNCATE ... RESTART IDENTITY` leaves the
    sequence with `is_called` false: the first `nextval` returns 1 and leaves `last_value` at 1, so
    a value of two or more means at least two ids were taken.
    """
    with database.connect() as connection:
        return int(connection.execute(text("SELECT last_value FROM link_id_seq")).scalar_one())


def test_the_same_url_twice_answers_one_code_and_leaves_one_row(
    client: TestClient, database: Engine
) -> None:
    """
    Given a URL that has already been shortened,
    when it is shortened again,
    then the second answer is 200 rather than 201, it is byte for byte the first one, and `link`
    still holds exactly one row.

    The bodies being **identical** is what says the existing row came back rather than a new link
    being made for the same URL: `created_at` is stamped by the clock at creation, so a second
    creation could not reproduce it.
    """
    target = TargetUrlMother.accepted()

    first = client.post("/links", json={"url": target})
    second = client.post("/links", json={"url": target})

    assert first.status_code == HTTPStatus.CREATED
    assert second.status_code == HTTPStatus.OK
    assert second.json() == first.json()
    assert "location" not in second.headers
    assert _count(database, "link") == 1


def test_two_different_urls_are_two_links(client: TestClient, database: Engine) -> None:
    """
    Given two URLs that differ,
    when each is shortened,
    then there are two rows and two codes.

    The control the test above needs. Without it, a repository that answered every lookup with the
    first row it ever stored would pass deduplication perfectly and be catastrophically wrong.
    """
    first = client.post("/links", json={"url": TargetUrlMother.accepted()})
    second = client.post("/links", json={"url": TargetUrlMother.another_accepted()})

    assert first.status_code == HTTPStatus.CREATED
    assert second.status_code == HTTPStatus.CREATED
    assert first.json()["code"] != second.json()["code"]
    assert _count(database, "link") == 2


def test_the_loser_of_the_race_is_refused_without_raising_and_reads_the_winner(
    database_dsn: str, database: Engine
) -> None:
    """
    Given one request that has passed the lookup and taken an id,
    when another request commits the same URL before it inserts,
    then its insert comes back False rather than raising, and the re-read hands it the winner.

    The deterministic version of the race, with the window opened by hand between step 2 and step
    3 -- no threads, no sleeps, nothing that can go flaky, and the losing branch exercised on every
    single run. The concurrent test below cannot promise that: it proves the invariant holds under
    real contention, but on an unlucky scheduling every request could take the fast path and the
    branch would never run.

    The engine is built by `create_database_engine`, which is not incidental. That function pins
    `READ COMMITTED`, and under `REPEATABLE READ` this test would not merely fail -- the losing
    `INSERT` would raise `SerializationFailure` and step 4 would never be reached at all.
    """
    engine = create_database_engine(database_dsn)
    factory = create_session_factory(engine)
    target = TargetUrlMother.accepted()
    digest = hash_url(target)

    try:
        with factory.begin() as session:
            loser = LinkRepositoryImpl(session)

            # Step 2 of the flow: nothing points at this URL yet, so the fast path is not taken.
            assert loser.find_by_url_hash(digest) is None

            # Step 3, first half: the id is spent. From here on this request is committed to
            # inserting, and the row it would write no longer describes what the database holds.
            loser_id = loser.next_id()

            # The race, in one block: another request does the whole flow and commits, inside the
            # window this one has open.
            with factory.begin() as rival_session:
                winner_id = LinkRepositoryImpl(rival_session).next_id()
                assert (
                    LinkRepositoryImpl(rival_session).save(
                        LinkMother.with_id(winner_id, url=target), url_hash=digest
                    )
                    is True
                )

            # Step 3, second half: `ON CONFLICT (url_hash) DO NOTHING` suppresses the violation, so
            # losing arrives as a value and never as an `IntegrityError` crossing the port.
            assert loser.save(LinkMother.with_id(loser_id, url=target), url_hash=digest) is False

            # Step 4: the re-read. It sees the winner because each statement under READ COMMITTED
            # takes a fresh snapshot -- the same transaction, and deliberately not the same
            # snapshot.
            winner = loser.find_by_url_hash(digest)
            assert winner is not None
            assert winner.id == winner_id
            assert winner.id != loser_id
    finally:
        engine.dispose()

    assert _count(database, "link") == 1


def test_eight_simultaneous_requests_for_one_url_create_exactly_one_link(
    client: TestClient, database: Engine
) -> None:
    """
    Given eight requests released at the same instant with the same URL,
    when they all run,
    then exactly one answers 201, the other seven answer 200, every one of them carries the same
    code, and `link` holds one row.

    The test the roadmap calls the most valuable one in the project, and the reason is that it is
    **impossible to write with a mock**: what is under test is what PostgreSQL does when two
    transactions insert the same key, which no in-memory double can be asked about.

    `threading.Barrier` rather than eight threads started in a loop. Starting them in a loop lets
    the first finish before the last begins, which is not a race; the barrier holds every thread
    until all eight have arrived and releases them together.

    The last assertion is what keeps this test from passing vacuously. If every request had taken
    the fast path -- found the link already there and returned it -- the four assertions above
    would still hold, and nothing would have raced. More than one id spent means more than one
    request got past the lookup and into the window that only the unique index closes.
    """
    target = TargetUrlMother.accepted()
    barrier = threading.Barrier(RACERS)

    def shorten() -> Any:
        barrier.wait()
        return client.post("/links", json={"url": target})

    with ThreadPoolExecutor(max_workers=RACERS) as pool:
        responses = [future.result() for future in [pool.submit(shorten) for _ in range(RACERS)]]

    statuses = Counter(response.status_code for response in responses)

    assert statuses[HTTPStatus.CREATED] == 1
    assert statuses[HTTPStatus.OK] == RACERS - 1
    assert len({response.json()["code"] for response in responses}) == 1
    assert _count(database, "link") == 1
    assert _ids_spent(database) > 1
