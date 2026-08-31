"""Use case implementations, one file per use case.

Each receives its ports through the constructor. No global state, no framework, no singleton.

There is one module here that is not a use case: `link_lookup.py`. It holds the single step both
read use cases take -- turning a path segment into the link it names, or into "not found" -- and it
is shared rather than duplicated because the `try` inside it has to stay exactly one expression
wide. Two copies of that would be two chances to widen it and answer 404 to something that
deserved 400.
"""
