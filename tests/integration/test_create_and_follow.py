"""The happy path, end to end: shorten a URL, follow the code, read what the link knows.

The first of the three tests this project is judged by. Everything below goes through HTTP into the
real application and comes back out through a real PostgreSQL, and the assertions that matter are
the ones about **rows**, not about response bodies -- a redirect answering 302 proves the routing,
and only the table proves the write.
"""

from datetime import UTC, datetime
from http import HTTPStatus

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from tests.integration.conftest import BASE_URL
from tests.mothers import TargetUrlMother
from url_shortener.domain.service.url_hash import hash_url

pytestmark = pytest.mark.integration


def test_a_shortened_url_is_stored_and_redirects_back_to_itself(
    client: TestClient, database: Engine
) -> None:
    """
    Given an empty database,
    when a URL is shortened and the code that comes back is followed,
    then the answer is 201 with the code `0000001`, the row in `link` carries the URL as it was
    sent together with its digest, and following the code answers 302 with the target in Location.

    The code is asserted **exactly**, which the truncation between tests is what makes possible: a
    generator that returned the right shape and the wrong value would pass a test that only checked
    the length.
    """
    target = TargetUrlMother.accepted()

    created = client.post("/links", json={"url": target})

    assert created.status_code == HTTPStatus.CREATED
    assert created.json()["code"] == "0000001"
    assert created.json()["short_url"] == f"{BASE_URL}/0000001"
    assert created.headers["location"] == f"{BASE_URL}/links/0000001"

    with database.connect() as connection:
        row = connection.execute(text("SELECT id, code, url, url_hash, created_at FROM link")).one()

    assert row.id == 1
    assert row.code == "0000001"
    assert row.url == target
    assert row.url_hash == hash_url(target)

    followed = client.get("/0000001")

    assert followed.status_code == HTTPStatus.FOUND
    assert followed.headers["location"] == target
    assert followed.headers["cache-control"] == "no-store"


def test_the_stored_timestamp_is_aware_and_close_to_now(
    client: TestClient, database: Engine
) -> None:
    """
    Given a link created through the API,
    when its `created_at` is read straight out of the column,
    then it carries an offset and it is within a minute of now.

    This is the one assertion the unit suite structurally cannot make. There the clock is frozen,
    so `created_at` is whatever the fake reported and the column is a dictionary key; here the
    value crosses `SystemClock`, psycopg and `TIMESTAMPTZ` and comes back. A naive datetime
    reaching the database is the classic silent Python date bug -- it only surfaces when two
    machines disagree about what "now" was -- and this is where it would be caught.
    """
    client.post("/links", json={"url": TargetUrlMother.accepted()})

    with database.connect() as connection:
        created_at = connection.execute(text("SELECT created_at FROM link")).scalar_one()

    assert created_at.utcoffset() is not None
    assert abs((datetime.now(UTC) - created_at).total_seconds()) < 60


def test_the_click_total_counts_the_redirects_that_happened(client: TestClient) -> None:
    """
    Given a link that has been followed three times,
    when its details are read,
    then `total_clicks` is 3 -- counted from the rows, since there is no counter column to drift.

    Reading the details records nothing, which the fourth number proves: asking how many times a
    link was followed is not following it, and a read that counted would change the answer by being
    asked for it.
    """
    code = client.post("/links", json={"url": TargetUrlMother.accepted()}).json()["code"]

    for _ in range(3):
        client.get(f"/{code}")

    details = client.get(f"/links/{code}")

    assert details.status_code == HTTPStatus.OK
    assert details.json()["total_clicks"] == 3
    assert client.get(f"/links/{code}").json()["total_clicks"] == 3


def test_an_unknown_code_answers_404_in_this_api_s_own_envelope(client: TestClient) -> None:
    """
    Given a database with no links in it,
    when a well-formed code that names nothing is followed,
    then the answer is 404 as a problem document, and not a redirect to nowhere.
    """
    response = client.get("/zzzzzzz")

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["type"] == "link-not-found"


def test_a_refused_target_spends_no_id_from_the_sequence(client: TestClient) -> None:
    """
    Given a URL the domain policy refuses,
    when it is posted and then an acceptable URL is posted after it,
    then the refusal answers 400 and the link that follows still gets `0000001`.

    The order of two lines in `CreateLinkUseCaseImpl` is what this pins, and nothing else can. A
    sequence does not obey rollback: `nextval` is spent even inside a transaction that aborts, so
    validating *after* taking the id would leave a permanent gap for every rejected request --
    invisible in every response, and visible only here, in the code the next link gets.
    """
    refused = client.post("/links", json={"url": TargetUrlMother.refused()})

    assert refused.status_code == HTTPStatus.BAD_REQUEST
    assert refused.json()["reason"] == "non-public-address"

    accepted = client.post("/links", json={"url": TargetUrlMother.accepted()})

    assert accepted.json()["code"] == "0000001"
