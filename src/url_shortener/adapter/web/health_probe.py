"""What `GET /health` needs to be able to ask.

A `Protocol` beside its consumer, which is the same rule the driven ports follow one layer in: the
side that asks the question owns the shape of it. What is different here is *which* layer that is.

**This is deliberately not a port in `application.port.outbound`.** `/health` is not a use case.
No inbound port names it, no use case runs it, and the application layer has no reason to know that
this endpoint exists at all -- putting the protocol there would grow the innermost layer to serve an
operational detail, which is the direction this architecture exists to prevent. ADR-0008.

The answer is a `bool` and not an exception, and that is what keeps `adapter/web/` free of any
import from SQLAlchemy: the controller needs exactly one bit to choose between 200 and 503, and the
side that knows what an `OperationalError` means is the side that logs it.
"""

from typing import Protocol


class HealthProbe(Protocol):
    """Whether the dependency this service reports on is answering."""

    def is_reachable(self) -> bool:
        """`True` if the dependency answered, `False` if it did not.

        It must not raise. A probe that failed by raising would land in the generic handler as a
        500, which is precisely the answer the health contract rules out.
        """
        ...
