"""A link, on its way out of the application."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class LinkResult:
    """What `POST /links` answers with, and the boundary the domain stops at.

    `code` is a `str` and not a `ShortCode`: this is the outbound edge, so the domain type is left
    behind here rather than in the controller. That is exactly what `ShortCode.__str__` is for.

    There is no `short_url`. Building it needs the public origin, which is a setting, and the
    application must never guess the host it is reachable on. The web adapter joins `BASE_URL` and
    `code`.

    There is no `id` either, for the plain reason that no response body in the API contract carries
    one -- and not because publishing it would leak anything, since `code` *is* the id in base 62
    and enumerable codes are already an accepted, documented cost of V1.

    `was_created` is the whole of the 201-versus-200 decision, in past tense so that it cannot be
    misread against the `created_at` on the line above. `201` means a link was created; `200` means
    an existing one came back, and the caller can tell.
    """

    code: str
    url: str
    created_at: datetime
    was_created: bool
