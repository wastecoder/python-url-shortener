"""The two sides of the hexagon, declared as `typing.Protocol`.

Protocols and not ABCs: an adapter satisfies one structurally, without importing or inheriting from
this package, which is exactly what keeps the dependency arrow pointing inward.
"""
