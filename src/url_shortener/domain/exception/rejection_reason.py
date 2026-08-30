"""The taxonomy of target URL refusals."""

from enum import StrEnum


class RejectionReason(StrEnum):
    """Why the target URL policy refused a URL. One member per kind of refusal.

    It lives here rather than next to the policy that raises it because
    `InvalidTargetUrlError` needs it in its own signature: with the enum in
    `domain.service.url_policy`, the exception would import the service and the service would
    import the exception, which is a cycle.

    Every member maps to the same problem type and the same status once it reaches the web
    adapter -- the reason is an extension member in the body, not a second status taxonomy.

    The values are written out instead of `auto()`, which on a `StrEnum` yields the lower-cased
    member name with underscores. The wire format of this API is hyphenated.
    """

    URL_TOO_LONG = "url-too-long"
    FORBIDDEN_CHARACTER = "forbidden-character"
    MALFORMED_URL = "malformed-url"
    MISSING_SCHEME = "missing-scheme"
    UNSUPPORTED_SCHEME = "unsupported-scheme"
    MISSING_HOST = "missing-host"
    CREDENTIALS_IN_URL = "credentials-in-url"
    NON_PUBLIC_HOST = "non-public-host"
    NON_PUBLIC_ADDRESS = "non-public-address"
