"""What the application needs a store of clicks to be able to do."""

from typing import Protocol

from url_shortener.domain.model.click import Click


class ClickRepository(Protocol):
    """Two methods, and the shape of the table they imply.

    Clicks are append-only: this port can write one and count them, and it deliberately offers no
    way to read one back, update one or delete one. A counter column on `link` would be a write on
    the read path, on the same row, so two hits on a popular link would contend for one row lock;
    an insert contends with nothing. The cost is paid on the cold path, by the `COUNT`, and that is
    the right trade at this scale.
    """

    def record(self, click: Click) -> None:
        """Append one access.

        The implementation issues the `INSERT` here, rather than staging it for a later commit at
        the edge. A redirect whose click is lost is a redirect that stopped being measured in
        silence -- and measurement is the whole reason this project answers 302 instead of 301,
        so the failure has to arrive while there is still a response to fail.
        """
        ...

    def count_by_link(self, link_id: int) -> int:
        """How many accesses this link has had.

        It takes the id and not the `Link`, because the id is what the foreign key and the index
        are on. Handing over a whole entity to read one integer would suggest the count is a
        property of the link, which is the belief that ends in a counter column.
        """
        ...
