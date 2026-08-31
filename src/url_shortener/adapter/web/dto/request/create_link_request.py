"""The body of `POST /links`."""

from pydantic import BaseModel, ConfigDict, Field


class CreateLinkRequest(BaseModel):
    """One field, and its type is the decision of this phase. See ADR-0005.

    `url` is a plain `str` and never `HttpUrl` or `AnyHttpUrl`, for three reasons that stack.

    Pydantic's URL types **normalise**. `https://example.com` comes back as
    `https://example.com/`. Rule 5 of this project says the URL is stored, hashed and redirected
    to exactly as it arrived, and rules 6 and 7 build deduplication on the SHA-256 of that string
    -- so a model that rewrites it would make the stored row stop being what the caller sent, and
    would quietly merge two URLs the domain treats as different.

    They also **decide policy**. `javascript:alert(1)` would come back as `422 validation-error`
    where the API contract says `400 invalid-target-url` carrying a machine-readable `reason`.
    Which URLs this shortener agrees to point at is decided in `domain.service.url_policy`, with
    nine refusal reasons and a hundred tests behind it, and a second validator that disagrees with
    it is the bug nobody finds until production.

    There is no `max_length` here for the same reason: the 2048-character limit belongs to that
    policy. Repeating it would leave two limits free to drift apart, and would answer 422 to
    something the contract answers 400 to.

    `extra="forbid"` so a field name typed wrong is a 422 instead of silence -- the same choice
    `Settings` makes about environment variables.
    """

    model_config = ConfigDict(extra="forbid")

    url: str = Field(
        description="The URL to shorten, stored and redirected to exactly as it is sent.",
        examples=["https://docs.python.org/3/library/dataclasses.html"],
    )
