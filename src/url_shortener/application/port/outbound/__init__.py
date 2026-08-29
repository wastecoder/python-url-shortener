"""Driven ports: what the application needs from the outside world.

`LinkRepository`, `ClickRepository` and `Clock`. Each one has a real implementation under `adapter`
and a fake under `tests`, and the use cases cannot tell the two apart -- which is the whole point
of declaring them here.
"""
