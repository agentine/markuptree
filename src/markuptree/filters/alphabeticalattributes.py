"""Filter that sorts element attributes alphabetically."""

from __future__ import annotations

from typing import Any, Dict, Iterator

from markuptree.filters.base import Filter


class Filter(Filter):
    """Sort attributes alphabetically on start/empty tags."""

    def __iter__(self) -> Iterator[Dict[str, Any]]:
        for token in self.source:
            if token["type"] in ("StartTag", "EmptyTag"):
                attrs = token.get("data", {})
                if attrs:
                    token = dict(token)
                    token["data"] = dict(sorted(attrs.items()))
            yield token
