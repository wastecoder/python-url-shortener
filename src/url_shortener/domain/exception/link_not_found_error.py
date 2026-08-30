"""No link exists for the requested code."""

from url_shortener.domain.exception.domain_error import DomainError


class LinkNotFoundError(DomainError):
    """The code does not resolve to any link.

    `code` is a plain `str` and not a `ShortCode`. The redirect route is a catch-all at the root,
    so any path at all reaches the application and has to be answered with "not found" rather than
    with a crash -- which means the value this error carries is frequently not a valid short code.
    Typing it as `ShortCode` would make the case that matters impossible to represent, and it
    would point `domain.exception` at `domain.model`.
    """

    def __init__(self, code: str) -> None:
        super().__init__(f"no link exists for code {code!r}")
        self.code = code
