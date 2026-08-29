"""Pure business rules. Imports nothing but the standard library.

No FastAPI, no SQLAlchemy, no Pydantic, no Starlette: everything here is testable with no
infrastructure running at all. The rule is enforced by the `domain-is-pure` contract in
`.importlinter`, not by good intentions.
"""
