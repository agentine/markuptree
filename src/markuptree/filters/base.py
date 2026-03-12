"""Base filter class for markuptree token stream filters."""

from __future__ import annotations

from typing import Any, Dict, Iterator


class Filter:
    """Base class for token stream filters.

    A filter wraps a token source (walker or another filter) and yields
    modified tokens.  Subclasses override ``__iter__`` to implement their
    transformation.
    """

    def __init__(self, source: Any) -> None:
        self.source = source

    def __iter__(self) -> Iterator[Dict[str, Any]]:
        yield from self.source

    def __getattr__(self, name: str) -> Any:
        return getattr(self.source, name)
