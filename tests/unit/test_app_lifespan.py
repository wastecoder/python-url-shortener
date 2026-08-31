"""The startup hook: what it builds, and that it lets go of it.

Nothing else in the suite exercises this. Every other test overrides the driven ports, so an
application whose lifespan stored no engine, built no session factory and disposed of nothing would
pass all of them -- and would fail on the first real request, in production, with an
`AttributeError` nobody could read.

It runs without a database. The DSN below points at an address in the reserved documentation range
and no connection is ever opened: building an engine does not connect, and neither does disposing
of one.
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from url_shortener.adapter.config.settings import Settings
from url_shortener.main import create_app

UNREACHABLE = "postgresql+psycopg://nobody:nothing@203.0.113.7:5432/nowhere"


@pytest.fixture
def settings() -> Settings:
    """Settings the application is handed, so that nothing reads the environment."""
    return Settings(_env_file=None, database_url=UNREACHABLE, base_url="https://sho.rt")


def test_the_startup_hook_publishes_everything_a_request_needs(settings: Settings) -> None:
    """
    Given an application built with explicit settings,
    when it starts up,
    then the settings, the engine, the session factory and the probe engine are all on app.state.

    A request reads three of these off `app.state`. One missing is not a wiring error a type
    checker can see -- `app.state` is untyped by design -- so it is an `AttributeError` inside a
    dependency, answered as an opaque 500.
    """
    app = create_app(settings=settings)

    with TestClient(app):
        assert app.state.settings is settings
        assert isinstance(app.state.engine, Engine)
        assert isinstance(app.state.session_factory, sessionmaker)
        assert isinstance(app.state.probe_engine, Engine)


def test_the_session_factory_is_bound_to_the_engine_that_was_built(settings: Settings) -> None:
    """
    Given a started application,
    when the session factory's bind is compared with the published engine,
    then they are the same object -- otherwise every request would run against an engine nobody
    disposes of.
    """
    app = create_app(settings=settings)

    with TestClient(app):
        assert app.state.session_factory.kw["bind"] is app.state.engine


def test_the_health_probe_gets_an_engine_of_its_own_with_no_pool(settings: Settings) -> None:
    """
    Given a started application,
    when the probe engine is compared with the request engine,
    then they are two different engines, and the probe's has no pool.

    This is the correction an adversarial review forced. While the two shared one engine they
    shared one `QueuePool`, so a pool exhausted by load made `/health` wait `pool_timeout` and then
    report the database as down -- a claim about this process's saturation, published as a claim
    about PostgreSQL. `NullPool` opens and closes a connection per check, which is what makes the
    connect timeout the real bound on how long the endpoint can take.
    """
    app = create_app(settings=settings)

    with TestClient(app):
        assert app.state.probe_engine is not app.state.engine
        assert isinstance(app.state.probe_engine.pool, NullPool)


def test_both_engines_are_disposed_on_shutdown(settings: Settings) -> None:
    """
    Given a started application,
    when it shuts down,
    then both engines are disposed.

    Without this, a reloader restarting the process on every file save leaves a pool of connections
    behind each time, and the database runs out of slots long before anybody connects the symptom
    to the cause.
    """
    app = create_app(settings=settings)
    disposed: list[str] = []

    with TestClient(app):
        for name in ("engine", "probe_engine"):
            engine: Engine = getattr(app.state, name)
            event.listen(
                engine,
                "engine_disposed",
                lambda _engine, _name=name: disposed.append(_name),
            )
        assert disposed == []

    assert sorted(disposed) == ["engine", "probe_engine"]


def test_an_application_given_settings_never_reads_the_environment(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    Given an application handed its settings,
    when it starts up and serves a request that needs BASE_URL,
    then the environment reader is never called.

    The reason this test exists is that it used to be false. `SettingsDep` called `get_settings()`
    on every request, so an application built with explicit settings still went to the environment,
    and a `POST /links` on a machine with no `.env` answered 500 -- hidden in the suite only
    because the conftest also overrode that provider. The startup hook now stores what it was
    given, and `SettingsDep` reads it back.
    """

    def explode(*_args: Any, **_kwargs: Any) -> Settings:
        raise AssertionError("the environment was read despite settings being supplied")

    monkeypatch.setattr("url_shortener.main.get_settings", explode)

    app = create_app(settings=settings)

    with TestClient(app) as client:
        assert client.get("/openapi.json").status_code == 200
        assert app.state.settings is settings
