"""The one failure this API reports about itself rather than about a request."""


class ServiceUnavailableError(Exception):
    """Something this service depends on is not answering, so it cannot serve.

    It lives in the web adapter and **not** in `domain.exception`, and the line is worth stating.
    Every exception in the domain names something about the business -- a target URL that was
    refused, a code that names no link -- and is deliberately ignorant of HTTP. "The database is
    down" is neither: it is not a rule, nothing in the domain could raise it, and it exists only
    because there is a process with dependencies.

    It does not extend `DomainError` for the same reason, which also keeps it out of reach of the
    one-expression `try` in `require_link`: a service that is down must never be reported as a
    missing link.

    `dependency` names what failed, in words a reader of the response can act on. It is the whole
    payload: no driver message, no host, no DSN. What is down is worth telling; how it is
    configured is not.
    """

    def __init__(self, dependency: str) -> None:
        self.dependency = dependency
        super().__init__(f"{dependency} is not answering")
