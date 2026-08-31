"""The taxonomy of `type` values this API answers with."""

from enum import StrEnum


class ProblemType(StrEnum):
    """One member per kind of failure, and the value is exactly what goes on the wire.

    A `StrEnum` of slugs, which is the same shape `RejectionReason` has, and for the same reason:
    the member name is for the code to read and the value is the wire format, so the two can never
    drift into each other.

    The status code is deliberately **not** here. It lives in the handler that answers each of
    these, one line each, because `HTTP_ERROR` has no single status: it covers the refusals the
    framework itself produces before any code of this project runs -- a 405 on the wrong method, a
    404 on a path no route matched -- so its status and its title come from the exception. Giving
    the enum a status column would mean one member carrying a hole, or a lie.

    The last three are three different things and the splits are worth the extra members:
    `INTERNAL_ERROR` is this API **failing**, `HTTP_ERROR` is this API **refusing**, and
    `SERVICE_UNAVAILABLE` is this API **unable to serve** because something it depends on is not
    answering. Only the first is a bug in this API, and only the third is worth taking an instance
    out of a load balancer's rotation for. ADR-0006 and ADR-0008.
    """

    INVALID_TARGET_URL = "invalid-target-url"
    VALIDATION_ERROR = "validation-error"
    LINK_NOT_FOUND = "link-not-found"
    HTTP_ERROR = "http-error"
    SERVICE_UNAVAILABLE = "service-unavailable"
    INTERNAL_ERROR = "internal-error"
