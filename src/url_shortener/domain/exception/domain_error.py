"""The root of the domain error hierarchy."""


class DomainError(Exception):
    """Base class for every error a business rule can raise.

    It extends `Exception` directly and **not** `ValueError`. The two say different things here: a
    `ValueError` means a value object was built wrong, which on every trusted path is a bug, while
    a `DomainError` means the caller broke a rule the API has to explain back to them. Making one
    a subclass of the other would let a single `except` clause swallow both and answer the wrong
    thing.

    Nothing in this hierarchy knows what a status code is. Turning a domain error into a response
    is the job of `adapter.web.handler`.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message
