"""Request bodies and query parameters.

Validated by Pydantic before a use case is ever called, which is why a malformed payload answers
422 while a rule violation answers 400.
"""
