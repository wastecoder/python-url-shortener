"""Driving adapter: HTTP.

Controllers, request and response models, and the RFC 7807 error handlers. The routers are
registered in `main`, and the catch-all redirect route must be registered last or it swallows
`/links`, `/health` and `/docs`.
"""
