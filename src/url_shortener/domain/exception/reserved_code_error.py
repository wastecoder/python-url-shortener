"""The code is one the API keeps for its own routes."""

from url_shortener.domain.exception.domain_error import DomainError


class ReservedCodeError(DomainError):
    """A code that would shadow a route of the API itself.

    Unreachable in V1, and that is the point: a generated code always has exactly seven
    characters and no reserved word has exactly seven, so the generator cannot produce one. This
    is the guard for a future path that *chooses* a code instead of generating it -- a custom
    alias, an import, a bug in the generator.

    `code` is a `str` for a reason that follows from the same fact: a reserved word is not seven
    characters long, so it can never be a `ShortCode`.
    """

    def __init__(self, code: str) -> None:
        super().__init__(f"short code {code!r} is reserved by the API")
        self.code = code
