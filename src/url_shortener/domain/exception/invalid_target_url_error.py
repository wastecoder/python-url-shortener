"""The target URL was refused by the domain policy."""

from url_shortener.domain.exception.domain_error import DomainError
from url_shortener.domain.exception.rejection_reason import RejectionReason


class InvalidTargetUrlError(DomainError):
    """A URL this shortener refuses to point at.

    It carries two different things on purpose. `reason` is the machine-readable taxonomy, stable
    enough for a client to branch on and for a test to assert without matching English. `message`
    is the sentence naming the offending scheme or host, which the taxonomy alone cannot say.
    """

    def __init__(self, reason: RejectionReason, message: str) -> None:
        super().__init__(message)
        self.reason = reason
