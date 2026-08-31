"""`GET /health`: what the service says about itself."""

from fastapi import APIRouter

from url_shortener.adapter.web.dto.response.health_response import HealthResponse

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Report whether the service is able to serve",
)
def health() -> HealthResponse:
    """Report the state of the service.

    Static in Fase 3, and that is a temporary honesty rather than the design. There is no
    dependency to check yet: the store is a dictionary inside this process, so anything this
    endpoint could ask it is already answered by the fact that the request arrived.

    From Fase 4 it runs `SELECT 1` against the database and answers `503` when that fails. A
    health check that always answers `200` is a lie, and it is exactly the difference between an
    endpoint a load balancer can trust and one that only proves the process is running.

    It has no dependencies of its own on purpose. A `/health` that needed the settings, a session
    or a use case to answer would be an endpoint that can fail for reasons unrelated to the health
    it reports.
    """
    return HealthResponse(status="ok")
