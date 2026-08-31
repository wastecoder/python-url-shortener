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

    **Its own connection, and never the request's session.** The health check must not be enlisted
    in the transaction it reports on -- it would then fail whenever the pool is exhausted, which is
    a fact about load and not about the database's health. It also has to be acquirable without
    failing, or the 503 branch becomes unreachable: a dependency whose *setup* raises does so before
    the controller body runs, and lands in the generic 500 handler instead.

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
        `logger.exception()`: the two are equivalent here, on the thread that caught it, and the
        explicit form is the one that stays correct if this is ever called from somewhere else --
        which is a mistake this codebase has already had to diagnose once, in the 500 handler.
        """
        try:
            with self._engine.connect() as connection:
                connection.execute(PING)
        except SQLAlchemyError as unreachable:
            _logger.warning("the database did not answer SELECT 1", exc_info=unreachable)
            return False
        return True
