"""The lookup key that deduplicates links: the SHA-256 of the target URL, in hexadecimal.

The unique index that closes the deduplication race is built on this value and never on the URL
itself. A PostgreSQL btree entry has a size limit of roughly 2.7 KB and a URL has no defined
length, so the index needs a key of fixed size -- a digest is exactly that, and it is the same 64
characters whether the URL is twelve bytes or two thousand.

The *index* is persistence, and `Link` says so; the *rule* -- that two requests mean the same link
when their URL strings are identical, byte for byte -- is a business rule, and it is the same rule
that makes `url_policy` normalise nothing. That is why the digest is computed here and not in the
repository: the repository would then own a decision about when two links are one.

This is not a security primitive. SHA-256 is used as a fixed-width key, and the URL it summarises
is stored in the clear in the column next to it.

Pure function: no state, no I/O, no clock. Only the standard library.
"""

import hashlib
from typing import NewType

# A `str` at runtime and a distinct type to a type checker. It does not contradict the decision
# that `find_by_url_hash` takes a plain `str` rather than an object -- a `NewType` *is* a `str`,
# it just is not *any* `str` -- and it buys the one mistake worth preventing here: handing the
# lookup the URL instead of its digest. That call is well typed as a plain `str`, finds nothing
# for ever, and writes a second row for a URL that already has one. Deduplication failing open,
# with nothing anywhere to notice.
UrlHash = NewType("UrlHash", str)


def hash_url(url: str) -> UrlHash:
    """Summarise a target URL into the fixed-size key its unique index is built on.

    The URL is encoded as UTF-8 explicitly, never with the platform default: the same URL must
    produce the same key on every machine that runs this code.
    """
    return UrlHash(hashlib.sha256(url.encode("utf-8")).hexdigest())
