"""Filter that collapses or strips inter-element whitespace."""

from __future__ import annotations

import re
from typing import Any, Dict, Iterator

from markuptree.constants import spaceCharacters
from markuptree.filters.base import Filter as BaseFilter

_SPACE_RE = re.compile(r"[\t\n\f\r ]+")

# Elements whose content is whitespace-sensitive.
_PRESERVE_WS = frozenset(["pre", "textarea", "script", "style"])


class Filter(BaseFilter):
    """Collapse runs of whitespace in text tokens.

    Whitespace inside ``<pre>``, ``<textarea>``, ``<script>``, and
    ``<style>`` is preserved.
    """

    def __iter__(self) -> Iterator[Dict[str, Any]]:
        preserve_depth = 0

        for token in self.source:
            ttype = token["type"]

            if ttype == "StartTag" and token["name"] in _PRESERVE_WS:
                preserve_depth += 1
            elif ttype == "EndTag" and token["name"] in _PRESERVE_WS:
                preserve_depth = max(0, preserve_depth - 1)

            if preserve_depth == 0 and ttype == "SpaceCharacters":
                token = dict(token)
                token["data"] = " "
            elif preserve_depth == 0 and ttype == "Characters":
                data = token["data"]
                collapsed = _SPACE_RE.sub(" ", data)
                if collapsed != data:
                    token = dict(token)
                    token["data"] = collapsed

            yield token
