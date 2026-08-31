"""Where the application gets the current instant."""

from datetime import datetime
from typing import Protocol


class Clock(Protocol):
    """The current instant, asked for rather than taken.

    `created_at` and `occurred_at` are owned by the domain and not by a column default, which is
    what makes them freezable: a test hands over a clock stuck at a known instant and then asserts
    the exact value that was written, instead of asserting that something roughly recent happened.

    The instant is always timezone aware -- `datetime.now(UTC)`, never `datetime.now()`. Both
    domain models refuse a naive value in `__post_init__`, so a clock that returns one fails
    where it is used rather than months later, when two machines disagree about what "now" was.
    """

    def now(self) -> datetime:
        """The current instant, timezone aware."""
        ...
