"""ADR-0007, checked against a real COMMIT instead of against a word in a signature.

The decision is that a redirect which fails to record its click must not answer `302`. Everything
about it was measurable except the one thing that mattered: the failure of the `COMMIT` itself.
`session.execute(insert(...))` raises inside the use case, so every *statement* failure was already
covered; the commit happens in the exit code of a `yield` dependency, and whether that runs before
or after the response leaves depends entirely on `scope="function"`.

Until now that word was guarded by a unit test which reads the `Depends` and asserts the string.
That test is worth keeping -- it fails the moment somebody deletes the argument -- but it proves
the word is present, not that the word works. This file poisons the commit and looks at what the
client gets, which is the version ADR-0007 itself calls "a versão da Fase 5 desta verificação".

**Why a deferred constraint and not a broken table.** The failure has to happen at `COMMIT` and
nowhere earlier: anything that makes the `INSERT` itself raise would be caught inside the use case
and would prove nothing about the boundary. PostgreSQL only defers `UNIQUE`, `PRIMARY KEY`,
`FOREIGN KEY` and `EXCLUDE`, so the poison is a unique constraint on `click(link_id)` -- "at most
one click per link" -- which is precisely the constraint this schema refuses to have, held back
until commit time.
"""

from collections.abc import Iterator
from http import HTTPStatus

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from tests.integration.conftest import CLIENT_ADDRESS, CLIENT_PORT
from tests.mothers import TargetUrlMother

pytestmark = pytest.mark.integration

_POISON = text(
    "ALTER TABLE click ADD CONSTRAINT tmp_one_click_per_link "
    "UNIQUE (link_id) DEFERRABLE INITIALLY DEFERRED"
)
_ANTIDOTE = text("ALTER TABLE click DROP CONSTRAINT tmp_one_click_per_link")


@pytest.fixture
def the_second_click_fails_at_commit(database: Engine) -> Iterator[None]:
    """Make a link's second click legal to insert and impossible to commit.

    `INITIALLY DEFERRED` is the whole mechanism: the uniqueness is not checked as the row is
    written but as the transaction ends, so the `INSERT` succeeds, the controller builds its
    redirect, and the violation surfaces at exactly the moment ADR-0007 is about.

    Dropped in the teardown rather than left to the truncation between tests, because `TRUNCATE`
    removes rows and not constraints -- a leaked one would make every later click in the session
    fail for a reason written in this file.
    """
    with database.begin() as connection:
        connection.execute(_POISON)
    try:
        yield
    finally:
        with database.begin() as connection:
            connection.execute(_ANTIDOTE)


@pytest.fixture
def tolerant_client(app: FastAPI) -> Iterator[TestClient]:
    """A client that lets a 500 come back as a response instead of re-raising it in the test.

    `raise_server_exceptions=False`, for the same reason the unit suite's problem-details tests
    need it: Starlette's `ServerErrorMiddleware` re-raises after the handler has produced its body,
    and the body is what is under test here.
    """
    with TestClient(
        app,
        follow_redirects=False,
        client=(CLIENT_ADDRESS, CLIENT_PORT),
        raise_server_exceptions=False,
    ) as client:
        yield client


def test_a_redirect_whose_commit_fails_answers_500_and_not_302(
    tolerant_client: TestClient,
    the_second_click_fails_at_commit: None,
    database: Engine,
) -> None:
    """
    Given a link that has already been followed once, and a constraint that will refuse its second
    click at commit time,
    when the code is followed again,
    then the caller gets a 500 problem document rather than a 302, and no second row exists.

    This is the decision of Fase 2 -- a failure to record the click brings the redirect down --
    turned into something observable from outside. With the session's exit code running after the
    response, which is what a `yield` dependency does by default in FastAPI, the caller would hold
    a `302 Location: https://...`, the browser would follow it, and the access would exist nowhere.
    Measured under all three scopes in ADR-0007: `"function"` answers 500, `"request"` and the
    default answer the success body.

    The negative cannot be demonstrated from inside this test, and that is worth knowing rather
    than working around: FastAPI reads the scope off the original `Depends`, so a
    `dependency_overrides` entry cannot put the wrong one back. The word is guarded by the unit
    test that reads it; this one guards what the word buys.
    """
    code = tolerant_client.post("/links", json={"url": TargetUrlMother.accepted()}).json()["code"]

    first = tolerant_client.get(f"/{code}")
    second = tolerant_client.get(f"/{code}")

    assert first.status_code == HTTPStatus.FOUND
    assert second.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    assert second.headers["content-type"] == "application/problem+json"
    assert second.json()["type"] == "internal-error"
    assert "location" not in second.headers

    with database.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM click")).scalar_one() == 1


def test_the_failed_transaction_leaves_the_database_usable(
    tolerant_client: TestClient,
    the_second_click_fails_at_commit: None,
    database: Engine,
) -> None:
    """
    Given a request whose commit has just failed,
    when the next request arrives,
    then it is served normally.

    The complement of the test above, and not a formality: a rolled-back transaction that left its
    connection poisoned would turn one failed commit into an outage. `sessionmaker.begin()` rolls
    back on the way out and the connection goes back to the pool clean, which is the reason the
    boundary is a context manager rather than four hand-written lines.
    """
    code = tolerant_client.post("/links", json={"url": TargetUrlMother.accepted()}).json()["code"]
    tolerant_client.get(f"/{code}")

    assert tolerant_client.get(f"/{code}").status_code == HTTPStatus.INTERNAL_SERVER_ERROR

    details = tolerant_client.get(f"/links/{code}")

    assert details.status_code == HTTPStatus.OK
    assert details.json()["total_clicks"] == 1
