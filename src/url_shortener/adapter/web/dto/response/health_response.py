"""The body of `GET /health`."""

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """What the service says about itself.

    `status` is a plain `str` and not a `Literal["ok"]`, because this endpoint is not finished. In
    Fase 3 there is no dependency to check, so it answers a static `ok`. From Fase 4 it runs
    `SELECT 1` against the database and answers `503` when that fails -- a health check that
    always answers `200` is a lie, and that is the whole difference between this endpoint and a
    placeholder.
    """

    status: str
