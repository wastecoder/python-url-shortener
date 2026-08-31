"""The click statements, compiled and read -- the two shapes the schema decisions turn into.

As with the link statements, nothing here runs: an integration test that follows a redirect and
finds one row in `click` would pass just as well against a counter column, which is the design this
project refuses. What is asserted is the SQL, because that is where the refusal is visible.
"""

from url_shortener.adapter.persistence.click_repository_impl import (
    count_statement,
    insert_click_statement,
)
from url_shortener.adapter.persistence.database.session import create_database_engine

DIALECT = create_database_engine(
    "postgresql+psycopg://nobody:nothing@203.0.113.7:5432/nowhere"
).dialect

VALUES: dict[str, object] = {
    "link_id": 7,
    "occurred_at": None,
    "user_agent": None,
    "referer": None,
    "ip": None,
}


def test_a_click_is_appended_unconditionally() -> None:
    """
    Given the statement that records an access,
    when it is compiled,
    then it is a plain INSERT with no conflict clause -- two identical accesses to the same link
    are two accesses, and an `ON CONFLICT DO NOTHING` here would drop the second one in silence.
    """
    sql = str(insert_click_statement(VALUES).compile(dialect=DIALECT))

    assert sql.startswith("INSERT INTO click")
    assert "ON CONFLICT" not in sql


def test_a_click_never_carries_an_id_it_was_given() -> None:
    """
    Given the same statement,
    when its column list is read,
    then `id` is absent: the column is BIGSERIAL and the database assigns it. A link is the
    opposite case, and deliberately so -- there the id is read first, because it is what the short
    code is computed from.
    """
    sql = str(insert_click_statement(VALUES).compile(dialect=DIALECT))

    assert sql.startswith("INSERT INTO click (link_id, occurred_at, user_agent, referer, ip)")


def test_the_total_is_counted_from_the_rows_that_exist() -> None:
    """
    Given the statement behind total_clicks,
    when it is compiled,
    then it counts rows of `click` filtered by link -- it never reads a column, on this table or on
    `link`, so the number cannot drift from the accesses it claims to summarise.
    """
    sql = str(count_statement(7).compile(dialect=DIALECT))

    assert "count(*)" in sql
    assert "FROM click" in sql
    assert "click.link_id = " in sql
    assert "FROM link" not in sql
