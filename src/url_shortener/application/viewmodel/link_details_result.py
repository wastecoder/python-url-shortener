"""A link and its click total, on the way out of the application."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class LinkDetailsResult:
    """What `GET /links/{code}` answers with.

    A separate type from `LinkResult`, and three repeated field declarations, for a behavioural
    reason rather than a tidy one. One shared result carrying both `was_created` and
    `total_clicks` would force the create use case to hold a `ClickRepository` and run a `COUNT`
    on the *write* path, to fill a field the `POST /links` body does not even contain -- or to
    hard-code a zero, which is true for a new link and a lie on the deduplication path.

    Flat rather than nesting a `LinkResult` inside it: nesting would save three lines and cost
    every reader a hop through `details.link.code`, and it would stop the response model of the
    web adapter being a field-for-field copy.
    """

    code: str
    url: str
    created_at: datetime
    total_clicks: int
