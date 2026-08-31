"""The one error body of this API: Problem Details, RFC 7807."""

from pydantic import BaseModel


class FieldError(BaseModel):
    """One field of a request body that failed validation.

    Built by hand out of `RequestValidationError.errors()` rather than passed through, and the
    difference matters. Pydantic's raw entries carry `input` and `ctx`: the first echoes the
    caller's own payload back at them, and both hold values that do not always survive JSON. Three
    fields is what a client needs to learn which field was wrong and why.
    """

    field: str
    message: str
    type: str


class ProblemResponse(BaseModel):
    """The envelope every failure of this API arrives in, served as `application/problem+json`.

    The first four members are the RFC's own, and they are required here even though the RFC
    makes them optional: a failure of this API always knows all four.

    `type` carries the slug exactly as the API contract writes it -- `invalid-target-url`, not a
    URN and not an absolute URL. The RFC calls the member a URI reference, and a relative one is
    legal; the trade accepted here is that it never becomes a dead link promising documentation
    nobody wrote.

    `instance` is the path the failure happened on. `reason` and `errors` are extension members,
    optional by definition in the RFC and present only where they say something -- they are
    serialised with `exclude_none=True`, so a 404 body carries neither instead of carrying two
    nulls.
    """

    type: str
    title: str
    status: int
    detail: str
    instance: str | None = None
    reason: str | None = None
    errors: list[FieldError] | None = None
