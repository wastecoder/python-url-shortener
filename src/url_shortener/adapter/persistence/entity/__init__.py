"""SQLAlchemy models, shaped by the database rather than by the domain.

They are deliberately a different type from `domain.model`: the domain must not inherit its shape
from the storage engine.
"""
