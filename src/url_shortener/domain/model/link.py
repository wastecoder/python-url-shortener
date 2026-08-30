"""A shortened link."""

from dataclasses import dataclass
from datetime import datetime

from url_shortener.domain.model.short_code import ShortCode


@dataclass(frozen=True, slots=True, kw_only=True)
class Link:
    """A target URL, the code that points at it, and the id that produced that code.

    `id` is not optional. It is read from the sequence *before* the insert, which is what allows
    the code to be computed here in the pure domain and the row to be written with `code NOT NULL`
    in a single statement. A link that does not know its id cannot exist.

    There is no `url_hash` field. The hash is a fixed-size key for a unique index -- a persistence
    concern -- and it is computed before any link exists, on the lookup that decides whether one
    has to be created at all. Storing it here would be a second copy of the same fact.

    Nothing here re-runs the target URL policy. The policy runs once, before the link exists;
    running it again on every read would turn a working redirect into a failure the day the policy
    gets stricter.
    """

    id: int
    code: ShortCode
    url: str
    created_at: datetime

    def __post_init__(self) -> None:
        if self.id < 1:
            raise ValueError(f"a link id comes from a sequence and starts at 1, got {self.id}")
        if not self.url.strip():
            raise ValueError("a link needs a target URL")
        if self.created_at.utcoffset() is None:
            raise ValueError(f"created_at must be timezone aware, got {self.created_at!r}")
