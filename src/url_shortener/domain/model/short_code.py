"""The public identifier of a link: exactly seven characters of the base 62 alphabet."""

from dataclasses import dataclass
from typing import Final, Self

from url_shortener.domain.service.base62 import ALPHABET, CODE_LENGTH, encode

_ALLOWED_CHARACTERS: Final[frozenset[str]] = frozenset(ALPHABET)


@dataclass(frozen=True, slots=True)
class ShortCode:
    """A code that has been checked, so that it and any other string are not the same type.

    It is deliberately not normalised. Base 62 is case sensitive, so `aaaaaaa` and `AAAAAAA` are
    two different links, and trimming blanks would let `" abcdef"` resolve the same link as
    `"abcdef"`.

    A violation raises `ValueError`, never a `DomainError`. A malformed code means the object was
    built wrong, which on the trusted paths -- the output of `encode`, a row read back from the
    database -- is a bug. The one untrusted path, the catch-all redirect route, turns it into
    "not found" on purpose, so a nonsense path is answered and not crashed on.
    """

    value: str

    def __post_init__(self) -> None:
        if len(self.value) != CODE_LENGTH:
            raise ValueError(
                f"a short code has exactly {CODE_LENGTH} characters, got {self.value!r}"
            )
        forbidden = sorted(set(self.value) - _ALLOWED_CHARACTERS)
        if forbidden:
            raise ValueError(
                f"a short code only uses the base 62 alphabet, and {self.value!r} "
                f"carries {forbidden}"
            )

    @classmethod
    def from_id(cls, link_id: int) -> Self:
        """Build the code that belongs to a link id read from the sequence.

        This is the only place where the model and the base 62 service meet, and it is why no
        use case ever has to import the encoding: it asks for the code of an id.
        """
        return cls(encode(link_id))

    def __str__(self) -> str:
        """Render the code itself, so an f-string builds a URL without reaching for `.value`."""
        return self.value
