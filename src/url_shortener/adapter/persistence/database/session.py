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
        # `CreateLinkUseCaseImpl` argues from it: under `REPEATABLE READ`, the re-read that follows
        # a lost deduplication race would keep the original snapshot and find nothing, which is the
        # branch that raises `RuntimeError`. A precondition that a line in `postgresql.conf` can
        # revoke is not a precondition.
        isolation_level="READ COMMITTED",
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
