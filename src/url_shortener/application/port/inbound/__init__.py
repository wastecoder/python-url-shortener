"""Driving ports: what the outside world may ask the application to do.

One Protocol per use case. Controllers depend on these, never on the `...Impl` classes.

Named `inbound` rather than `in` because `in` is a reserved keyword, and `application.port.in`
would be a syntax error on import. It is the only intentional deviation from the Java package
names this layout comes from.
"""
