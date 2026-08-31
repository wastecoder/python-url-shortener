"""`GET /health` against a database that is there, one that is not, and a pool that is full.

A health check that always answers 200 proves the process is running, which the arrival of the
request already proved. What makes this endpoint worth having is the two answers it can give and
the engine it gives them on, and neither is reachable from the unit suite: there the probe is a
stub whose `reachable` attribute a test flips, which checks the controller and nothing about
whether `SELECT 1` can actually be run.

The third test is ADR-0008 itself. The probe used to share the request engine, a review measured
what that cost, and the fix -- a second, poolless engine -- has had no test until now.
"""

import logging
from http import HTTPStatus

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Connection

from tests.integration.conftest import BASE_URL
from url_shortener.adapter.config.settings import Settings
from url_shortener.main import create_app

pytestmark = pytest.mark.integration

# A port nothing listens on, on the loopback interface. How long the attempt takes is the
# platform's business and not this project's -- measured on Windows it waits out the three-second
# `connect_timeout` rather than being refused outright -- and that is precisely the reason
# `connect_timeout` is set on the engine at all: it is the upper bound on how long this endpoint
# can take to answer "down". Port 1 is reserved and never bound.
UNREACHABLE_DSN = "postgresql+psycopg://nobody:nothing@127.0.0.1:1/nowhere"


def test_health_answers_ok_when_the_database_answers(client: TestClient) -> None:
    """
    Given a database that is up,
    when health is asked,
    then the answer is 200 and `ok` -- and it was earned by a round trip, not by the process being
    alive.
    """
    response = client.get("/health")

    assert response.status_code == HTTPStatus.OK
    assert response.json() == {"status": "ok"}


def test_health_answers_503_in_the_problem_envelope_when_the_database_is_gone(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """
    Given an application whose DSN points at nothing,
    when health is asked,
    then the answer is 503 as a problem document naming the database, the cause is nowhere in the
    body, and it is in the log with its traceback attached.

    503 and not 500, and the split is the whole reason `ServiceUnavailableError` exists: 500 means
    this API has a bug, 503 means this API is fine and something it needs is out. Only the second
    is worth taking an instance out of a load balancer's rotation for.

    The application is built here rather than taken from a fixture because the DSN is the subject.
    Nothing connects while it is being built -- `create_engine` opens no socket -- so the failure
    happens where it should, inside the endpoint.

    **The log assertion is load-bearing beyond this endpoint.** It is the only thing standing
    between this suite and a silent regression in `tests/integration/conftest.py`: build the
    Alembic configuration from `alembic.ini` instead of from an empty `Config`, and `env.py` calls
    `fileConfig`, which switches off every logger the ini does not name -- including this one, for
    the rest of the session. Measured: after that call, `DatabaseProbe`'s logger comes back with
    `disabled = True`. Without this line the regression would be invisible.
    """
    settings = Settings(_env_file=None, database_url=UNREACHABLE_DSN, base_url=BASE_URL)

    with caplog.at_level(logging.WARNING), TestClient(create_app(settings=settings)) as client:
        response = client.get("/health")

    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["type"] == "service-unavailable"
    assert response.json()["detail"] == "The database this service depends on is not answering."
    assert "nowhere" not in response.text

    logged = [record for record in caplog.records if record.name.startswith("url_shortener.")]

    assert [record.levelno for record in logged] == [logging.WARNING]
    assert logged[0].exc_info is not None


def test_health_still_answers_when_every_request_connection_is_taken(
    client: TestClient, app: FastAPI
) -> None:
    """
    Given every connection of the request pool checked out and held,
    when health is asked,
    then it answers 200 immediately.

    This is ADR-0008 as an observable fact. Sharing one engine between the requests and the probe
    reads like an economy and is a trap: a checkout from an exhausted `QueuePool` does not fail
    fast, it *waits* up to `pool_timeout` -- thirty seconds by default -- so under load `/health`
    would hang for half a minute and then report the database as down while the database was
    answering normally. A report about this process's saturation, dressed as a report about
    PostgreSQL.

    The probe engine is a `NullPool`, so it has no queue to wait in: it opens a connection, runs
    `SELECT 1`, and closes it.

    `_max_overflow` is read directly because SQLAlchemy publishes no reader for it. The capacity is
    asserted rather than assumed, so the day a pool setting changes this test says so instead of
    quietly holding half a pool and proving nothing.
    """
    pool = app.state.engine.pool
    capacity = pool.size() + pool._max_overflow

    assert capacity == 15

    held: list[Connection] = []
    try:
        held = [app.state.engine.connect() for _ in range(capacity)]

        assert pool.checkedout() == capacity

        response = client.get("/health")
    finally:
        for connection in held:
            connection.close()

    assert response.status_code == HTTPStatus.OK

    # The pool is handed back intact. It is asserted rather than assumed because the fifteen
    # connections above are the only place in this suite where one is held by hand, and a `finally`
    # that stopped working would not fail here -- it would fail somewhere later, as a test hanging
    # for thirty seconds on a pool that is full for a reason written in this file.
    assert pool.checkedout() == 0
