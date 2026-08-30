"""One access to a short link."""

from dataclasses import dataclass
from datetime import datetime
from ipaddress import IPv4Address, IPv6Address


@dataclass(frozen=True, slots=True, kw_only=True)
class Click:
    """An access to a link, written once and never touched again.

    There is no `id`. The table has one, but the domain never reads a click back on its own:
    clicks are append-only and the only question ever asked of them is how many belong to a link.
    A field nothing reads would only add another optional for every caller to think about.
    `Link.id` is the opposite case and is required, because there the id *is* the code generator.

    `user_agent`, `referer` and `ip` are optional because an HTTP client owes none of them. `ip`
    is an address object rather than text, so a value the domain accepted cannot fail later
    against a column that stores addresses.
    """

    link_id: int
    occurred_at: datetime
    user_agent: str | None = None
    referer: str | None = None
    ip: IPv4Address | IPv6Address | None = None

    def __post_init__(self) -> None:
        if self.link_id < 1:
            raise ValueError(f"a click points at a link id that starts at 1, got {self.link_id}")
        if self.occurred_at.utcoffset() is None:
            raise ValueError(f"occurred_at must be timezone aware, got {self.occurred_at!r}")
