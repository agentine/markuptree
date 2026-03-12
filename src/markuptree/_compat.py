"""Compatibility shim: ``import markuptree as html5lib``."""

# Re-export everything from the public API so that code doing
# ``import markuptree as html5lib`` or ``from markuptree import ...``
# sees the same names that html5lib exposes.

from markuptree import (  # noqa: F401
    __version__,
    parse,
    parseFragment,
    getTreeBuilder,
    getTreeWalker,
    serialize,
    HTMLParser,
    ParseError,
    SerializeError,
)

from markuptree.serializer import HTMLSerializer  # noqa: F401
from markuptree.treewalkers import getTreeWalker as getTreeWalker  # noqa: F811
from markuptree.treebuilders import getTreeBuilder as getTreeBuilder  # noqa: F811

# html5lib also had these aliases.
HTMLParseError = ParseError
