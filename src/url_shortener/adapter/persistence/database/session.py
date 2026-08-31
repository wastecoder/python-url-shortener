"""The engine and the session factory: where this adapter meets the driver.

Two plain functions and no module-level state. The engine is not a singleton created on import,
because a process that builds its connection pool as a side effect of an `import` is a process
whose tests cannot avoid it and whose startup order nobody controls. It is built once at startup by
the application's lifespan, which is also the only place that can dispose of it.

Nothing here imports FastAPI. The `Depends` wrapper around all of this lives in
`adapter/config/dependencies.py`, which is where wiring belongs.
"""

from typing import Final

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

# Seconds libpq waits for a connection before giving up. It exists mostly for `/health`: with no
# timeout, a host that accepts packets and never answers turns the health check into a request that
# hangs, which is worse than a health check that says "down" -- a load balancer can act on the
# second and can only wait on the first.
CONNECT_TIMEOUT_SECONDS: Final = 3


def create_database_engine(dsn: str) -> Engine:
    """Build the engine. It opens nothing: the first connection is made on first use.

    That laziness is load-bearing rather than incidental. It is what lets the application be built
    -- and the whole unit suite be run -- with a DSN pointing at a database that is not there.
    """
    return create_engine(
        dsn,
        # A `docker compose restart postgres` leaves the pool holding connections to a server that
        # is gone. Without this, the next request after a restart fails once, for a reason that is
        # nowhere in this codebase; with it, the dead connection is discarded and replaced.
        pool_pre_ping=True,
        # `READ COMMITTED` is already PostgreSQL's default, and it is pinned here anyway because
        # the deduplication flow only works under it. Measured against a real server: under
        # `REPEATABLE READ` the losing `INSERT ... ON CONFLICT (url_hash) DO NOTHING` does not come
        # back empty, it raises `SerializationFailure` -- so a request that lost the race would
        # answer 500 rather than the winning link. A precondition a line in `postgresql.conf` can
        # revoke is not a precondition.
        isolation_level="READ COMMITTED",
        connect_args={"connect_timeout": CONNECT_TIMEOUT_SECONDS},
    )


def create_probe_engine(dsn: str) -> Engine:
    """A second engine, for the health check and nothing else.

    It exists because sharing the request engine would make `/health` report on the wrong thing.
    A pool has a size, and a checkout from an exhausted one does not fail fast -- it **waits**, up
    to `pool_timeout`, which defaults to thirty seconds. Under load the health check would hang for
    half a minute and then answer `503` while the database was answering normally: a report about
    this process's saturation, dressed as a report about the database.

    `NullPool` means every call opens a connection and closes it. That is the wrong default for a
    request path and the right one here: one short statement, no state to keep warm, and
    `connect_timeout` as the real upper bound on how long the endpoint can take. `pool_pre_ping`
    would be meaningless -- there is no pooled connection to find stale.

    The cost is a connect per call, so a health check hit every second is a connection every
    second. At this scale that is cheaper than the failure it removes.
    """
    return create_engine(
        dsn,
        poolclass=NullPool,
        connect_args={"connect_timeout": CONNECT_TIMEOUT_SECONDS},
    )


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """The factory a request opens its one session from.

    `expire_on_commit` is left at its default deliberately. Entities never outlive the request:
    every row is converted to a domain object by the `mapper` package the moment it is read, long
    before the commit at the request edge, so there is nothing left attached for an expiry to
    affect. Setting it would be a knob configured against a case that cannot arise.
    """
    return sessionmaker(bind=engine)
