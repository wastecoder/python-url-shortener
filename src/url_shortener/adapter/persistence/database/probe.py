"""Asking the database whether it is there."""

import logging
from typing import Final

from sqlalchemy import Engine, TextClause, text
from sqlalchemy.exc import SQLAlchemyError

# The cheapest statement that proves a round trip actually happened. Checking that the pool has a
# connection object would prove nothing: a connection to a server that has gone away looks exactly
# like a healthy one until something is sent over it.
PING: Final[TextClause] = text("SELECT 1")

_logger = logging.getLogger(__name__)


class DatabaseProbe:
    """`SELECT 1`, on a connection of its own.

    **Its own engine, and never the request's session.** Two reasons, and the second was measured
    rather than assumed. The first: the health check must not be enlisted in the transaction it
    reports on. The second: a session draws from the request pool, and a checkout from an exhausted
    pool does not fail fast -- it *waits*, up to `pool_timeout` -- so a session-backed check would
    hang and then blame the database for this process being busy. The engine handed in here is
    poolless for exactly that reason.

    What is **not** a reason, although it reads like one and was written here first: that acquiring
    a session against a dead database would fail before the controller ran and be answered as a
    500. It would not. `sessionmaker.begin()` does not connect, so the failure would land on
    `execute`, inside the controller body, where it could have been caught.

    It does not inherit from `HealthProbe`. That protocol lives in the web adapter, and importing it
    here would tie persistence to the shape of a controller; conformance is structural, and
    `dependencies.py` is where a type checker reads it.
    """

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def is_reachable(self) -> bool:
        """Whether the database answered. Never raises.

        `SQLAlchemyError` is the whole hierarchy the driver's failures arrive in -- refused
        connection, timeout, authentication, a server that went away mid-statement -- and every one
        of them means the same thing to a caller of `/health`. Catching them individually would be a
        taxonomy nobody reads, and catching `Exception` would swallow bugs in this method.

        The cause goes to the log, not to the response. `exc_info=unreachable` rather than
        `logger.exception()`, and the two are **not** interchangeable: `logger.exception` also
        forces the level to ERROR, and a dependency being out is a WARNING here -- the endpoint
        answered, correctly, with the answer it exists to give. Passing `exc_info` explicitly also
        stays correct if this is ever called off the thread that caught the error, which is a
        mistake this codebase has already had to diagnose once, in the 500 handler.
        """
        try:
            with self._engine.connect() as connection:
                connection.execute(PING)
        except SQLAlchemyError as unreachable:
            _logger.warning("the database did not answer SELECT 1", exc_info=unreachable)
            return False
        return True
