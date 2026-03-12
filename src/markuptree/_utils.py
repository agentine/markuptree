"""Internal utility helpers for markuptree."""

from __future__ import annotations

import os
import re
from typing import Any


supports_unicode_filenames: bool = os.path.supports_unicode_filenames


def moduleFactoryFactory(factory: Any) -> Any:
    """Create a module factory (used by treebuilder/treewalker loading).

    This is a helper for the getTreeBuilder/getTreeWalker dispatch pattern
    inherited from html5lib.
    """
    moduleCache: dict[str, Any] = {}

    def moduleFactory(
        baseModule: Any, *args: Any, **kwargs: Any
    ) -> Any:
        name = baseModule.__name__
        if name not in moduleCache:
            moduleCache[name] = factory(baseModule, *args, **kwargs)
        return moduleCache[name]

    return moduleFactory


def _memoize(func: Any) -> Any:
    """Simple memoization decorator for zero-argument functions."""
    sentinel = object()
    result = sentinel

    def wrapper() -> Any:
        nonlocal result
        if result is sentinel:
            result = func()
        return result

    return wrapper


_RE_ENTITY = re.compile(r"&(#?)(x?)(\d+|[a-zA-Z]+);?")
