"""Base 62 conversion over the `0-9a-zA-Z` alphabet.

A short code is the sequence id of a link written in base 62 and left-padded with the zero digit
to exactly seven characters. `encode` and `decode` are inverses over `[0, MAX_ID]`, so a code and
an id name each other with nothing in between -- no lookup table, no collision, no second round
trip to the database.

Pure functions: no state, no I/O, no clock. Only the standard library.
"""

from typing import Final

ALPHABET: Final[str] = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
BASE: Final[int] = len(ALPHABET)
CODE_LENGTH: Final[int] = 7

# The largest id that still fits in seven characters. The annotation is not decorative:
# `int.__pow__` is typed as returning `Any`, so without `Final[int]` this name would be `Any`
# and every comparison against it would stop being checked.
MAX_ID: Final[int] = BASE**CODE_LENGTH - 1

# The reverse map, built from the alphabet itself so the two can never disagree. Looking a
# character up here is also what rejects everything outside the alphabet, with no `isalnum`
# heuristic that would happily accept a Unicode look-alike digit.
_DIGIT_VALUES: Final[dict[str, int]] = {char: value for value, char in enumerate(ALPHABET)}


def encode(link_id: int) -> str:
    """Write a link id in base 62, left-padded to exactly `CODE_LENGTH` characters."""
    if link_id < 0:
        raise ValueError(f"a link id is never negative, got {link_id}")
    if link_id > MAX_ID:
        raise ValueError(f"link id {link_id} does not fit in {CODE_LENGTH} base 62 characters")

    digits: list[str] = []
    remaining = link_id
    while remaining > 0:
        remaining, value = divmod(remaining, BASE)
        digits.append(ALPHABET[value])
    # An id of zero leaves `digits` empty on purpose: the padding is what turns "" into "0000000".
    return "".join(reversed(digits)).zfill(CODE_LENGTH)


def decode(code: str) -> int:
    """Read a short code back into the link id that produced it.

    Strict on purpose. Accepting a code of any length would break the other half of the bijection:
    a lenient `decode("1")` is 1, whose code is "0000001", and one link would answer to two names.
    """
    if len(code) != CODE_LENGTH:
        raise ValueError(f"a short code has exactly {CODE_LENGTH} characters, got {code!r}")

    link_id = 0
    for char in code:
        value = _DIGIT_VALUES.get(char)
        if value is None:
            raise ValueError(f"{char!r} is not a base 62 digit")
        link_id = link_id * BASE + value
    return link_id
