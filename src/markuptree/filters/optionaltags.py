"""Filter that omits optional start/end tags per the HTML spec."""

from __future__ import annotations

from collections import deque
from typing import Any, Dict, Iterator, Optional

from markuptree.filters.base import Filter as BaseFilter

# Tags whose end tag can be omitted if immediately followed by certain tokens.
# See HTML spec section 13.1.2.4 "Optional tags".
_OMIT_END = {
    "html", "head", "body", "li", "dt", "dd", "p",
    "optgroup", "option", "colgroup",
    "thead", "tbody", "tfoot", "tr", "td", "th",
    "rt", "rp",
}

# Tags whose start tag can be omitted.
_OMIT_START = {"html", "head", "body", "colgroup", "tbody"}

# Elements that, when they follow a <p>, cause the <p>'s end tag to be omittable.
_P_CLOSERS = frozenset([
    "address", "article", "aside", "blockquote", "details", "dialog",
    "dir", "div", "dl", "fieldset", "figcaption", "figure", "footer",
    "form", "h1", "h2", "h3", "h4", "h5", "h6", "header", "hgroup",
    "hr", "main", "menu", "nav", "ol", "p", "pre", "section", "table", "ul",
])


class Filter(BaseFilter):
    """Omit optional start and end tags where the HTML spec allows it."""

    def __iter__(self) -> Iterator[Dict[str, Any]]:
        # Use a lookahead buffer so we can peek at the next token.
        buf: deque[Dict[str, Any]] = deque()
        for token in self.source:
            buf.append(token)
            if len(buf) >= 2:
                yield from self._maybe_omit(buf)
        # Flush remaining.
        while buf:
            yield buf.popleft()

    def _maybe_omit(self, buf: deque) -> Iterator[Dict[str, Any]]:
        while len(buf) >= 2:
            current = buf[0]
            nxt = buf[1]

            if current["type"] == "EndTag" and current["name"] in _OMIT_END:
                if self._can_omit_end(current["name"], nxt):
                    buf.popleft()
                    continue

            yield buf.popleft()

    def _can_omit_end(self, name: str, nxt: Dict[str, Any]) -> bool:
        ntype = nxt["type"]
        nname = nxt.get("name", "")

        if name == "li":
            return (ntype == "StartTag" and nname == "li") or (
                ntype == "EndTag" and nname in ("ul", "ol")
            )
        if name == "dt":
            return ntype == "StartTag" and nname in ("dt", "dd")
        if name == "dd":
            return (ntype == "StartTag" and nname in ("dt", "dd")) or (
                ntype == "EndTag" and nname == "dl"
            )
        if name == "p":
            return ntype in ("StartTag", "EmptyTag") and nname in _P_CLOSERS
        if name == "option":
            return (ntype == "StartTag" and nname in ("option", "optgroup")) or (
                ntype == "EndTag" and nname in ("select", "datalist", "optgroup")
            )
        if name == "optgroup":
            return (ntype == "StartTag" and nname == "optgroup") or (
                ntype == "EndTag" and nname == "select"
            )
        if name in ("thead", "tbody", "tfoot"):
            return (ntype == "StartTag" and nname in ("thead", "tbody", "tfoot")) or (
                ntype == "EndTag" and nname == "table"
            )
        if name == "tr":
            return (ntype == "StartTag" and nname == "tr") or (
                ntype == "EndTag" and nname in ("thead", "tbody", "tfoot", "table")
            )
        if name in ("td", "th"):
            return (ntype == "StartTag" and nname in ("td", "th")) or (
                ntype == "EndTag" and nname in ("tr", "thead", "tbody", "tfoot", "table")
            )
        if name == "colgroup":
            if ntype == "SpaceCharacters":
                return False
            return ntype != "Comment"
        if name == "head":
            return ntype != "SpaceCharacters" or ntype == "EndTag"
        if name in ("html", "body"):
            # html/body end tags can be omitted when followed by nothing problematic.
            return True

        return False
