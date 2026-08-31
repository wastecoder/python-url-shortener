"""The body of `GET /links/{code}`."""

from datetime import datetime
from typing import Self

from pydantic import BaseModel

from url_shortener.adapter.web.public_url import short_url
from url_shortener.application.viewmodel.link_details_result import LinkDetailsResult


class LinkDetailsResponse(BaseModel):
    """A link, its age, and how often it has been followed.

    A separate model from `LinkResponse` rather than one model with an optional `total_clicks`,
    for the same reason `LinkDetailsResult` is a separate viewmodel: an optional field would let
    the creation response advertise a click total it never computes, and avoiding that lie would
    put a `COUNT` on the write path.
    """

    code: str
    short_url: str
    url: str
    created_at: datetime
    total_clicks: int

    @classmethod
    def from_result(cls, result: LinkDetailsResult, *, base_url: str) -> Self:
        """Render a use case result as this API's JSON."""
        return cls(
            code=result.code,
            short_url=short_url(result.code, base_url=base_url),
            url=result.url,
            created_at=result.created_at,
            total_clicks=result.total_clicks,
        )
