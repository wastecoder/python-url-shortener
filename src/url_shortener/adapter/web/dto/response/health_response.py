"""The body of `GET /health`."""

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """What the service says about itself.

    This is the **success** body and the only one it has: the endpoint runs `SELECT 1` against the
    database, and a database that does not answer produces a `503` in the API's Problem Details
    envelope instead of a different shape of this model. So `status` has exactly one value on the
    wire today, `"ok"`.

    It is nevertheless a plain `str` and not a `Literal["ok"]`. A `Literal` would say that this
    service can only ever report one thing about itself, and the moment a second dependency exists
    -- a cache, an object store -- a degraded-but-serving answer becomes a real state, distinct
    from both `200 ok` and `503`. Widening the type then would change the published schema; leaving
    it open costs nothing now.
    """

    status: str
