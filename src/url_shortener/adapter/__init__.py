"""Everything that talks to a technology. The only layer allowed to know a framework exists.

Driving adapters (`web`) call into `application.port.inbound`. Driven adapters (`persistence`)
implement `application.port.outbound`.
"""
