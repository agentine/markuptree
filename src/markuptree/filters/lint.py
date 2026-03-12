"""Lint filter that checks for common serialization issues."""

from __future__ import annotations

from typing import Any, Dict, Iterator

from markuptree.constants import namespaces, voidElements
from markuptree.filters.base import Filter as BaseFilter


class Filter(BaseFilter):
    """Check token stream for issues and emit SerializeError tokens."""

    def __iter__(self) -> Iterator[Dict[str, Any]]:
        open_elements: list[str] = []

        for token in self.source:
            ttype = token["type"]

            if ttype == "StartTag":
                name = token["name"]
                if name in voidElements:
                    yield {
                        "type": "SerializeError",
                        "data": f"Void element <{name}> used as StartTag instead of EmptyTag",
                    }
                open_elements.append(name)
                yield token

            elif ttype == "EmptyTag":
                name = token["name"]
                if name not in voidElements:
                    yield {
                        "type": "SerializeError",
                        "data": f"Non-void element <{name}> used as EmptyTag",
                    }
                yield token

            elif ttype == "EndTag":
                name = token["name"]
                if name in voidElements:
                    yield {
                        "type": "SerializeError",
                        "data": f"Void element <{name}> has an end tag",
                    }
                elif open_elements and open_elements[-1] == name:
                    open_elements.pop()
                elif name in open_elements:
                    yield {
                        "type": "SerializeError",
                        "data": f"End tag </{name}> does not match current open element",
                    }
                yield token

            else:
                yield token
