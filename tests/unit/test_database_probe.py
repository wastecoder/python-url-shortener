"""Both branches of the health probe, with no Docker and no PostgreSQL.

The engines here are SQLite, and that is not a shortcut. What is under test is the probe's
plumbing -- does a round trip that works answer `True`, does one that cannot even open answer
`False` instead of raising, and is the cause recorded -- and none of that is dialect specific.
`SELECT 1` is the same statement everywhere. Whether *PostgreSQL* answers it is Fase 5's business,
and no unit test can stand in for that.

The `False` branch matters more than the `True` one. It is the branch that only ever runs when the
database is down, so it is exactly the branch that stays untested unless a test goes looking for
it -- and a health check whose failure path has never run is a health check nobody has seen work.
"""

import logging
from pathlib import Path

import pytest
from sqlalchemy import create_engine

from url_shortener.adapter.persistence.database.probe import DatabaseProbe


def _reachable() -> DatabaseProbe:
    """A probe over an in-process database that answers."""
    return DatabaseProbe(create_engine("sqlite://"))


def _unreachable(tmp_path: Path) -> DatabaseProbe:
    """A probe over a database file that cannot be opened, because it is a directory.

    An in-process failure, so nothing here touches the network or waits on a timeout.
    """
    return DatabaseProbe(create_engine(f"sqlite:///{tmp_path}"))


def test_a_database_that_answers_is_reachable() -> None:
    """
    Given a database that responds,
    when the probe pings it,
    then it reports reachable -- which is what makes /health answer 200.
    """
    assert _reachable().is_reachable() is True


def test_a_database_that_cannot_be_opened_is_not_reachable(tmp_path: Path) -> None:
    """
    Given a database that cannot be opened at all,
    when the probe pings it,
    then it reports unreachable rather than raising.

    Not raising is the requirement, not a nicety: an exception escaping here would be caught by the
    generic handler and answered as 500, and the whole point of this endpoint is that a dependency
    being out is a 503.
    """
    assert _unreachable(tmp_path).is_reachable() is False


def test_the_reason_it_failed_is_recorded_on_the_server(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """
    Given a database that cannot be opened,
    when the probe pings it,
    then the driver's error is written to the log with its traceback.

    The response says only which dependency is down. Somebody still has to be able to find out
    *why*, and this is the only place that knows -- so a probe that swallowed the cause silently
    would turn every outage into a guess.
    """
    with caplog.at_level(logging.WARNING):
        _unreachable(tmp_path).is_reachable()

    assert len(caplog.records) == 1
    assert caplog.records[0].levelno == logging.WARNING
    assert caplog.records[0].exc_info is not None


def test_a_healthy_probe_logs_nothing(caplog: pytest.LogCaptureFixture) -> None:
    """
    Given a database that answers,
    when the probe pings it,
    then nothing is logged -- a health check hit once a second by a load balancer must not be a
    line in the log once a second.
    """
    with caplog.at_level(logging.DEBUG):
        _reachable().is_reachable()

    assert caplog.records == []
