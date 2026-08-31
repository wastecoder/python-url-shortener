"""`GET /health`: what the service says about itself."""

from http import HTTPStatus
from typing import Final

from fastapi import APIRouter

from url_shortener.adapter.config.dependencies import HealthProbeDep
from url_shortener.adapter.web.dto.response.health_response import HealthResponse
from url_shortener.adapter.web.dto.response.problem_response import ProblemResponse
from url_shortener.adapter.web.handler.service_unavailable_error import ServiceUnavailableError

router = APIRouter(tags=["health"])

# The one dependency this service has, named in the words the response uses.
DEPENDENCY: Final = "database"


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Report whether the service is able to serve",
    responses={
        HTTPStatus.SERVICE_UNAVAILABLE: {
            "model": ProblemResponse,
            "description": "The database this service depends on is not answering.",
        },
    },
)
def health(probe: HealthProbeDep) -> HealthResponse:
    """Report the state of the service, by asking the thing it depends on.

    A health check that always answers `200` is a lie: it proves the process is running, which the
    arrival of the request already proved. This one runs `SELECT 1` and answers `503` when that
    fails, which is the difference between an endpoint a load balancer can act on and a placeholder.

    **It depends on exactly one thing, and that thing is what it reports on.** Until Fase 4 it
    declared no dependency at all, on the principle that an endpoint needing a session or a use case
    to answer could fail for reasons unrelated to the health it reports. The principle survives; the
    conclusion changed, because now there is something real to check. What replaces it is narrower
    and does more work: the probe opens a connection of its own, so `/health` is not enlisted in the
    request transaction and cannot fail because the pool is busy -- and acquiring it cannot fail
    either, which is what keeps the `503` branch reachable. A dependency whose *setup* raises does
    so before this function runs, and would be answered as `500`. ADR-0008.

    The probe returns a `bool` rather than raising, which is why this module imports no SQLAlchemy:
    the question "is the database answering" is the entire contract, and what an `OperationalError`
    means is knowledge that stays on the other side of it.
    """
    if not probe.is_reachable():
        raise ServiceUnavailableError(DEPENDENCY)
    return HealthResponse(status="ok")
