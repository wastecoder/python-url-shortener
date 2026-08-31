"""From a `Click` to a row of `click`. There is no way back, and that is the design.

`ClickRepository` can append a click and count clicks, and offers no way to read one, update one or
delete one. So there is no `to_domain` here: a function nothing calls would be an invitation to
start reading clicks back, which is the first step towards a report this project deliberately does
not have.
"""

from url_shortener.domain.model.click import Click


def to_values(click: Click) -> dict[str, object]:
    """The column values of the row this click becomes.

    No `id`: `click.id` is `BIGSERIAL` and the database assigns it. The domain has no field for it
    either, because nothing ever reads a click back to ask which one it was.

    `ip` crosses unconverted, in an `INET` column. psycopg 3 knows `ipaddress` objects in both
    directions by default, so the address the domain holds is the address the driver writes -- and
    `str(click.ip)` here would be a conversion whose only effect is to make the read side need a
    matching one back.
    """
    return {
        "link_id": click.link_id,
        "occurred_at": click.occurred_at,
        "user_agent": click.user_agent,
        "referer": click.referer,
        "ip": click.ip,
    }
