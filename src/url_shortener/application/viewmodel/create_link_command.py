"""What a caller asks for when it asks for a link."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CreateLinkCommand:
    """The one thing `POST /links` carries: a URL to point at.

    Nothing here validates it. `validate_target_url` runs as the first statement of the use case,
    so "no effect happens before the target is accepted" stays a property of the use case rather
    than of whoever happened to build the command. A command that validated itself would let a
    second caller construct one and skip the rule.

    One field, so no `kw_only`: there is no neighbouring field to swap it with. This is also the
    type that grows when V2 adds a custom alias, which is the argument for it existing while a
    plain `str` parameter would still do.
    """

    url: str
