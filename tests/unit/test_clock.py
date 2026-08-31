"""The system clock: aware, in UTC, and moving forward."""

from datetime import UTC, datetime

from url_shortener.adapter.config.clock import SystemClock
from url_shortener.application.port.outbound.clock import Clock


def _clock() -> Clock:
    """Build the subject annotated with the port: the return type is the conformance assertion."""
    return SystemClock()


def test_the_instant_is_timezone_aware() -> None:
    """
    Given the system clock,
    when it is asked for the current instant,
    then the value carries an offset, which is what both domain models require.
    """
    assert _clock().now().utcoffset() is not None


def test_the_instant_is_in_utc() -> None:
    """
    Given the system clock,
    when it is asked for the current instant,
    then the instant is expressed in UTC and not in the offset of whatever machine runs it.
    """
    assert _clock().now().tzinfo is UTC


def test_the_instant_is_the_current_one() -> None:
    """
    Given the system clock,
    when it is asked for the current instant,
    then the answer sits between two readings of the wall clock taken around the call.
    """
    before = datetime.now(UTC)
    instant = _clock().now()
    after = datetime.now(UTC)

    assert before <= instant <= after


def test_two_readings_never_go_backwards() -> None:
    """
    Given the system clock,
    when it is read twice,
    then the second reading is not earlier than the first, so a click cannot predate its link.
    """
    clock = _clock()

    first = clock.now()
    second = clock.now()

    assert second >= first
