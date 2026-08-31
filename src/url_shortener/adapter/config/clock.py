"""The real clock, behind the `Clock` port."""

from datetime import UTC, datetime


class SystemClock:
    """The current instant, always timezone aware.

    The `UTC` argument is the whole class. `datetime.now()` without it returns a naive value: it
    reads correctly, stores silently, and only surfaces months later, when two machines disagree
    about what "now" was. Both `Link` and `Click` refuse a naive instant in `__post_init__`, so
    the job here is to make sure they never see one.

    It holds no state and could have been a plain function. It is a class because the port is a
    `Protocol` with a `now` method, and because the wiring hands over an object annotated with
    the port -- which is what turns the conformance into something `mypy` checks rather than
    something a comment claims.

    There is no `SystemClock` in the tests. A test that needs a known instant uses `FixedClock`,
    which is exactly the substitution the port exists for.
    """

    def now(self) -> datetime:
        """The current instant, in UTC."""
        return datetime.now(UTC)
