"""The engine and the session factory, asserted without a database in sight.

The point of this file is the laziness. `create_app` builds an engine at startup from a DSN it was
handed, and the entire unit suite runs against an application built that way -- so "building an
engine opens no connection" is not a curiosity about SQLAlchemy, it is the property that keeps
`uv run pytest` runnable with no Docker and no PostgreSQL anywhere.
"""

from sqlalchemy import Engine

from url_shortener.adapter.persistence.database.session import (
    create_database_engine,
    create_session_factory,
)

UNREACHABLE = "postgresql+psycopg://nobody:nothing@203.0.113.7:5432/nowhere"


def test_building_an_engine_opens_no_connection() -> None:
    """
    Given a DSN pointing at an address in the reserved documentation range, which answers nothing,
    when an engine is built from it,
    then the call returns instead of raising.

    Reaching the end of this test *is* the assertion. An eager connection here would spend the
    three-second connect timeout and then fail, so a `create_database_engine` that opened a socket
    could not make this test pass -- and the application, whose lifespan builds an engine at
    startup, could not be constructed anywhere its database is absent.
    """
    engine = create_database_engine(UNREACHABLE)

    assert isinstance(engine, Engine)
    assert engine.url.render_as_string(hide_password=False) == UNREACHABLE


def test_the_engine_speaks_postgresql_over_psycopg() -> None:
    """
    Given the DSN this project uses,
    when the engine is built,
    then the dialect and the driver are the ones the whole design assumes: `ON CONFLICT`, `INET`
    and `nextval` are PostgreSQL, and the `ipaddress` round trip is psycopg 3.
    """
    engine = create_database_engine(UNREACHABLE)

    assert engine.dialect.name == "postgresql"
    assert engine.dialect.driver == "psycopg"


def test_the_session_factory_is_bound_to_the_engine_it_was_given() -> None:
    """
    Given an engine,
    when a session is opened from the factory built around it,
    then that session would run its statements on that engine -- the assertion that the two halves
    the lifespan builds are actually connected to each other.
    """
    engine = create_database_engine(UNREACHABLE)

    with create_session_factory(engine)() as session:
        assert session.get_bind() is engine
