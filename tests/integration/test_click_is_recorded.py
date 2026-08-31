"""The redirect's side effect: a row in `click`, and the schema that makes it contention-free.

The third of the three headline tests, and the one that is about an **effect** rather than a return
value. `GET /{code}` answers 302 whether or not the access was recorded; only the table says which.
That is the sentence that rules a mocked repository out of this file -- a mock would let a test
assert that `record` was called, which is a fact about this codebase and not about the database.
"""

from datetime import UTC, datetime
from http import HTTPStatus
from ipaddress import IPv4Address

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from tests.integration.conftest import CLIENT_ADDRESS
from tests.mothers import TargetUrlMother

pytestmark = pytest.mark.integration

REFERER = "https://example.net/whence"
USER_AGENT = "curl/8.5.0"


def _shorten(client: TestClient) -> str:
    """Shorten the stock target and hand back its code."""
    return str(client.post("/links", json={"url": TargetUrlMother.accepted()}).json()["code"])


def test_following_a_link_appends_one_fully_described_row_to_click(
    client: TestClient, database: Engine
) -> None:
    """
    Given a link and a request carrying a user agent and a referer,
    when the code is followed,
    then `click` holds one row pointing at that link, stamped with an aware instant and carrying
    the peer address as an `INET` value, the user agent and the referer.

    The address is asserted as an `IPv4Address` and not as text on purpose. The column is `INET`
    and psycopg 3 registers loaders for `ipaddress` by default, so what comes back out is already
    an address object -- which is exactly why the mapper converts nothing in either direction, and
    a test comparing against a string here would be asserting the wrong contract.
    """
    code = _shorten(client)

    response = client.get(f"/{code}", headers={"user-agent": USER_AGENT, "referer": REFERER})

    assert response.status_code == HTTPStatus.FOUND

    with database.connect() as connection:
        row = connection.execute(
            text("SELECT link_id, occurred_at, user_agent, referer, ip FROM click")
        ).one()

    assert row.link_id == 1
    assert row.user_agent == USER_AGENT
    assert row.referer == REFERER
    assert row.ip == IPv4Address(CLIENT_ADDRESS)
    assert row.occurred_at.utcoffset() is not None
    assert abs((datetime.now(UTC) - row.occurred_at).total_seconds()) < 60


def test_a_request_without_the_optional_headers_still_records_a_click(
    client: TestClient, database: Engine
) -> None:
    """
    Given a request that sends no referer,
    when the code is followed,
    then the row is written all the same and the column holds NULL rather than an empty string.

    An HTTP client owes neither header. A click with no referer is a click, not an error, and the
    absence has to survive as an absence -- an empty string would be a value the caller never sent.
    """
    code = _shorten(client)

    client.get(f"/{code}", headers={"user-agent": USER_AGENT})

    with database.connect() as connection:
        referer = connection.execute(text("SELECT referer FROM click")).scalar_one()

    assert referer is None


def test_every_access_is_a_new_row_and_nothing_is_ever_updated(
    client: TestClient, database: Engine
) -> None:
    """
    Given a link followed three times,
    when the table is read,
    then there are three rows with three distinct ids, and the first one is exactly as it was
    written.

    `click` is append-only, and this is what that means from outside: three accesses are three
    rows. A design that kept a total on `link` would show one row and a counter, which is a write
    on the read path, on the same row, that two hits on a popular link contend for.
    """
    code = _shorten(client)

    for _ in range(3):
        client.get(f"/{code}")

    with database.connect() as connection:
        rows = connection.execute(text("SELECT id, link_id FROM click ORDER BY id")).all()

    assert len(rows) == 3
    assert len({row.id for row in rows}) == 3
    assert {row.link_id for row in rows} == {1}


def test_the_link_table_has_no_column_that_could_hold_a_total(database: Engine) -> None:
    """
    Given the schema the migrations produced,
    when the columns of `link` are read out of the catalogue,
    then they are exactly the five the design names -- and none of them is a click counter.

    The decision this asserts is not visible from any response: an API with a counter column and an
    API counting rows answer `total_clicks` identically. It is checked against
    `information_schema`, which describes what the migration actually built, rather than against
    the entity, which only describes what somebody wrote down.
    """
    with database.connect() as connection:
        columns = set(
            connection.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name = 'link'")
            ).scalars()
        )

    assert columns == {"id", "code", "url", "url_hash", "created_at"}
