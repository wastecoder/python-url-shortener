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

    `INTERNAL_ERROR` and `HTTP_ERROR` are not the same thing and the split is worth the extra
    member: the first is this API failing, the second is this API refusing. Only the first is a
    bug.
    """

    INVALID_TARGET_URL = "invalid-target-url"
    VALIDATION_ERROR = "validation-error"
    LINK_NOT_FOUND = "link-not-found"
    HTTP_ERROR = "http-error"
    INTERNAL_ERROR = "internal-error"
