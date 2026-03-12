"""Tree walker backends for markuptree."""

from __future__ import annotations

from typing import Any


def getTreeWalker(name: str, implementation: Any = None, **kwargs: Any) -> Any:
    """Get a TreeWalker class by name.

    Supported names: ``"etree"``, ``"dom"``, ``"lxml"``, ``"genshi"``.
    """
    name = name.lower()
    if name == "etree":
        from . import etree
        return etree.TreeWalker
    elif name == "dom":
        from . import dom
        return dom.TreeWalker
    elif name == "lxml":
        from . import etree_lxml
        return etree_lxml.TreeWalker
    elif name == "genshi":
        from . import genshi
        return genshi.TreeWalker
    else:
        raise ValueError(f"Unknown tree walker: {name!r}")
