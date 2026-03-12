"""Compatibility shim: ``import markuptree as html5lib``."""

# Re-export everything from the public API so that code doing
# ``import markuptree as html5lib`` or ``from markuptree import ...``
# sees the same names that html5lib exposes.

from markuptree import (  # noqa: F401
    parse,
    parseFragment,
    getTreeBuilder,
    getTreeWalker,
    serialize,
    HTMLParser,
    ParseError,
    SerializeError,
)
