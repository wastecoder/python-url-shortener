"""Driving ports: what the outside world may ask the application to do.

One Protocol per use case. Controllers depend on these, never on the `...Impl` classes.

Named `inbound` rather than `in` because `in` is a reserved keyword, and `application.port.in`
would be a syntax error on import. It is the only intentional deviation from the Java package
names this layout comes from.

Each port names its own verb -- `create`, `resolve`, `get_details` -- and none of them declares a
uniform `execute`. The reason is structural rather than stylistic: a `Protocol` has no nominal
identity, so the method name *is* the type's identity. Three ports all declaring `execute` are
three shapes that one class can satisfy by accident, and the wiring file handing the wrong
implementation to the right controller would type-check. A `__call__` collapses the port into a
plain callable and does it on top of that.

Nothing in this package imports `domain`, and a contract in `.importlinter` says so. The signature
a controller reads is written entirely in viewmodels and built-in types, which is what makes the
web adapter unable to reach a domain object even by accident.
"""
