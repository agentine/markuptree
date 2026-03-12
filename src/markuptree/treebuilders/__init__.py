"""Tree builder backends for markuptree."""

from __future__ import annotations

from typing import Any


def getTreeBuilder(name: str, implementation: Any = None, **kwargs: Any) -> Any:
    """Get a TreeBuilder class by name.

    Supported names: ``"etree"``, ``"dom"``, ``"lxml"``.
    """
    name = name.lower()
    if name == "etree":
        from . import etree
        return etree.TreeBuilder
    elif name == "dom":
        from . import dom
        return dom.TreeBuilder
    elif name == "lxml":
        from . import etree_lxml
        return etree_lxml.TreeBuilder
    else:
        raise ValueError(f"Unknown tree builder: {name!r}")
