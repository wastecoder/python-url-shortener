"""Fixtures for the integration tests: one real PostgreSQL, migrated, for the whole session.

The mirror image of `tests/unit/conftest.py`, and the contrast is the reason both exist. There the
three driven ports are replaced by fakes and nothing ever opens a socket; here **nothing is
overridden at all**. The repositories are `LinkRepositoryImpl` and `ClickRepositoryImpl`, the
session is the one `get_session` opens, the transaction commits where ADR-0007 says it does, and
the health probe runs a real `SELECT 1`. What is under test is the database's behaviour, so a mock
anywhere in the path would make the whole suite prove nothing.

**The schema comes from the migrations, never from `Base.metadata.create_all()`.** That is the only
thing that tests the migrations at all: a schema built from the models is a schema no migration was
ever run against, and the day one of them is wrong is the day production finds out.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.pool import NullPool
from testcontainers.community.postgres import PostgresContainer

from url_shortener.adapter.config.settings import Settings
from url_shortener.main import create_app

# The same image `compose.yml` pins, to the same patch. A suite that tests against a different
# server than the one anybody runs is a suite that can pass while the product is broken.
#
# The version is 18.6 because that is what `compose.yml` pins -- 18 is the release that moved the
# official image's `PGDATA` -- and deliberately not because anything below needs a server that new.
# Nothing here leans on a recent feature, so this suite would keep passing against an older major:
# what it is pinned to is *parity with the thing being shipped*, which is the only property worth
# having.
POSTGRES_IMAGE = "postgres:18.6-alpine"

# The origin the short URLs are built from, fixed here rather than read from anywhere. It is
# deliberately not a real host: nothing in this suite follows a redirect off the application.
BASE_URL = "https://sho.rt"

# A routable address for the peer, for the same reason the unit suite fixes one: the test client
# otherwise reports the literal string `testclient`, which does not parse as an address, so every
# click in the suite would store `NULL` and the `INET` column would never be exercised.
CLIENT_ADDRESS = "203.0.113.7"
CLIENT_PORT = 51234

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_MIGRATIONS = _REPOSITORY_ROOT / "migrations"


def alembic_config(dsn: str) -> Config:
    """An Alembic configuration pointing at this repository's migrations and at `dsn`.

    **Built empty and filled in, rather than read from `alembic.ini`**, and the reason is a side
    effect rather than a preference. `migrations/env.py` calls `fileConfig` whenever it was handed
    a file, and `fileConfig` defaults to `disable_existing_loggers=True` -- it switches off every
    logger the ini does not name. In production that is harmless, because `alembic upgrade head`
    runs in a process of its own and exits. Here it would run *inside the test process*, after
    `url_shortener.*` has been imported, and would silence `DatabaseProbe`'s logger for the rest of
    the session -- a fixture quietly changing the behaviour of the code under test.

    Everything that decides *what runs* is still the real thing: the same `migrations/` directory,
    the same `env.py`, the same revision scripts. Only the logging configuration is left out, and
    only because this process already has one.

    Setting `sqlalchemy.url` in memory is the hook `env.py` and `alembic.ini` were both written for:
    the DSN of a container on a random port never touches a versioned file.
    """
    config = Config()
    config.set_main_option("script_location", str(_MIGRATIONS))
    config.set_main_option("sqlalchemy.url", dsn)
    return config


@pytest.fixture(scope="session")
def database_dsn() -> Iterator[str]:
    """A PostgreSQL container with this project's migrations applied, for the whole session.

    Session-scoped because starting a container costs seconds and applying the migrations costs
    more; per-test isolation is bought by `empty_tables` below, which costs a `TRUNCATE`.

    `driver="psycopg"` is not optional. `PostgresContainer` defaults to `psycopg2`, which this
    project does not depend on, so the default DSN would name a driver that is not installed --
    and the failure arrives as an import error from inside SQLAlchemy, far from the line that
    chose it.
    """
    with PostgresContainer(POSTGRES_IMAGE, driver="psycopg") as container:
        dsn = container.get_connection_url()
        command.upgrade(alembic_config(dsn), "head")
        yield dsn


@pytest.fixture(scope="session")
def database(database_dsn: str) -> Iterator[Engine]:
    """An engine for the tests themselves, separate from every engine the application builds.

    Separate on purpose. A test that inspected the database through the application's own session
    would be reading inside the transaction it is trying to observe from outside, and would see
    writes that have not committed -- which is exactly the failure mode the three headline tests
    exist to rule out.

    `NullPool` so the suite never holds connections between tests: the pool the tests exercise is
    the application's, and a second one sitting idle on the same server's connection budget would
    be noise inside it.
    """
    engine = create_engine(database_dsn, poolclass=NullPool)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture(autouse=True)
def empty_tables(database: Engine) -> None:
    """Both tables emptied and the id sequence restarted, before every test.

    `TRUNCATE`, and not `DELETE`, because it is one statement that also resets the sequence.
    `RESTART IDENTITY` is what makes the first link of every test come back as `0000001`, so an
    assertion can name the exact code instead of comparing two codes to each other -- and a test
    that names the code is a test that would catch a generator producing the wrong one.

    **No `CASCADE`.** Both tables are listed, which is what PostgreSQL requires when one references
    the other, so `CASCADE` would add nothing today and would silently truncate whatever table
    somebody adds tomorrow without listing it here.

    It runs *before* each test rather than after, so a test starts from a known state even when the
    one before it failed halfway through.
    """
    with database.begin() as connection:
        connection.execute(text("TRUNCATE link, click RESTART IDENTITY"))


@pytest.fixture
def settings(database_dsn: str) -> Settings:
    """Settings pointing at the container, built here rather than read from the environment.

    `_env_file=None` keeps a developer's local `.env` out of the run. Without it the DSN below
    would be overridden by whatever database that developer happens to have running, and the suite
    would quietly stop testing the container it just started.
    """
    return Settings(_env_file=None, database_url=database_dsn, base_url=BASE_URL)


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    """The real application, wired to the container, with **nothing** overridden.

    Per test rather than per session: `create_app` is cheap, and an application shared across tests
    would share one connection pool -- the pool that
    `test_health_still_answers_when_every_request_connection_is_taken` checks out to its last
    connection by hand, and the pool the eight racers of the concurrency test run against. (Those
    eight do *not* fill it: `RACERS` is bounded at eight against a capacity of fifteen precisely so
    that the test keeps measuring PostgreSQL and not `pool_timeout`.)
    """
    return create_app(settings=settings)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    """A client that never follows a redirect and reports a routable address.

    `follow_redirects=False` is not a preference, and the reason is **not** the network -- which
    is what this paragraph used to say, until it was measured. The test client dispatches every
    request through its one ASGI transport whatever host the URL names, so the hop never leaves the
    process and no name is ever resolved. It re-enters *this* application, where
    `https://example.com/a-fairly-long-target` matches the catch-all `GET /{code}`, finds no link
    and answers `404`. The `302` and its `Location` would then be buried in `response.history`
    while `response` carried that `404`, and every assertion naming them would be reading the
    wrong answer.

    The `with` block is what runs the ASGI lifespan, and here that matters more than it does in the
    unit suite -- the lifespan is where the settings are resolved and where both engines are built.
    Without it `app.state.session_factory` would not exist and every request would fail on an
    attribute error.
    """
    with TestClient(
        app, follow_redirects=False, client=(CLIENT_ADDRESS, CLIENT_PORT)
    ) as test_client:
        yield test_client
