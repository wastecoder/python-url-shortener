"""Smoke test: the src layout is installed and the package resolves."""

import importlib


def test_the_package_is_importable() -> None:
    """
    Given the src layout and an editable install,
    when `url_shortener` is imported,
    then it resolves and carries its module docstring.
    """
    module = importlib.import_module("url_shortener")

    assert module.__doc__ is not None
