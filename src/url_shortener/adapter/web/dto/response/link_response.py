"""The body of `POST /links`."""

from datetime import datetime
from typing import Self

from pydantic import BaseModel

from url_shortener.adapter.web.public_url import short_url
from url_shortener.application.viewmodel.link_result import LinkResult


class LinkResponse(BaseModel):
    """A link on the wire: what the caller asked for, plus the short URL built for it.

    `short_url` is the one field with no counterpart in `LinkResult`, and it cannot have one:
    building it needs the public origin, which is a setting the application layer is not allowed
    to know about.

    `was_created` has no counterpart here either, deliberately and in the other direction. It is
    carried by the **status code** -- `201` when a link was created, `200` when an existing one
    came back -- so repeating it in the body would be one fact in two places, free to disagree.

    `from_result` reads a viewmodel, which is the legal direction: `adapter -> application`. The
    mirror image is what ADR-0004 forbids, and it is why converting a `Link` into a `LinkResult`
    is a private function of the use case instead of a constructor on the viewmodel.
    """

    code: str
    short_url: str
    url: str
    created_at: datetime

    @classmethod
    def from_result(cls, result: LinkResult, *, base_url: str) -> Self:
        """Render a use case result as this API's JSON."""
        return cls(
            code=result.code,
            short_url=short_url(result.code, base_url=base_url),
            url=result.url,
            created_at=result.created_at,
        )
