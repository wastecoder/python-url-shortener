"""Composition root: settings, dependency wiring, and the concrete `Clock`.

The only package allowed to know both a port and its implementation. Everything is wired here,
exactly once.
"""
