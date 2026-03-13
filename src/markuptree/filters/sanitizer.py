"""Sanitizer filter that strips unsafe elements and attributes."""

from __future__ import annotations

from typing import Any, Dict, FrozenSet, Iterator, Optional, Set

from markuptree.filters.base import Filter as BaseFilter

# Safe elements allowed through the sanitizer.
_SAFE_ELEMENTS = frozenset([
    "a", "abbr", "acronym", "address", "area", "article", "aside",
    "b", "bdi", "bdo", "big", "blockquote", "body", "br",
    "caption", "center", "cite", "code", "col", "colgroup",
    "data", "dd", "del", "details", "dfn", "dir", "div", "dl", "dt",
    "em",
    "figcaption", "figure", "font", "footer",
    "h1", "h2", "h3", "h4", "h5", "h6", "head", "header", "hr", "html",
    "i", "img", "ins",
    "kbd",
    "li", "link",
    "main", "map", "mark", "menu", "meta",
    "nav",
    "ol",
    "p", "pre",
    "q",
    "rp", "rt", "ruby",
    "s", "samp", "section", "small", "span", "strike", "strong",
    "sub", "summary", "sup",
    "table", "tbody", "td", "tfoot", "th", "thead", "time", "title", "tr", "tt",
    "u", "ul",
    "var",
    "wbr",
])

# Safe attributes allowed through the sanitizer.
_SAFE_ATTRS = frozenset([
    "abbr", "accept", "accept-charset", "accesskey", "action",
    "align", "alt", "axis", "border",
    "cellpadding", "cellspacing", "char", "charoff", "charset",
    "checked", "cite", "class", "clear", "cols", "colspan",
    "color", "compact", "coords",
    "datetime", "dir", "disabled", "enctype",
    "for", "frame",
    "headers", "height", "href", "hreflang", "hspace",
    "id", "ismap",
    "label", "lang", "longdesc",
    "maxlength", "media", "method", "multiple",
    "name", "nohref", "noshade", "nowrap",
    "prompt",
    "readonly", "rel", "rev", "rows", "rowspan", "rules",
    "scope", "selected", "shape", "size", "span", "src", "start",
    "summary",
    "tabindex", "target", "title", "type",
    "usemap",
    "valign", "value", "vspace",
    "width",
    "xml:lang",
])

# Attributes that may contain URIs.
_URI_ATTRS = frozenset(["action", "background", "cite", "href", "longdesc", "src"])

# Safe URI schemes.
_SAFE_SCHEMES = frozenset([
    "http", "https", "mailto", "ftp", "ftps", "tel",
])


class Filter(BaseFilter):
    """Strip elements and attributes that are not on the allow list."""

    def __init__(
        self,
        source: Any,
        allowed_elements: Optional[FrozenSet[str]] = None,
        allowed_attrs: Optional[FrozenSet[str]] = None,
    ) -> None:
        super().__init__(source)
        self.allowed_elements = allowed_elements or _SAFE_ELEMENTS
        self.allowed_attrs = allowed_attrs or _SAFE_ATTRS

    def __iter__(self) -> Iterator[Dict[str, Any]]:
        strip_depth = 0
        for token in self.source:
            ttype = token["type"]

            if ttype in ("StartTag", "EmptyTag"):
                name = token["name"]
                if name not in self.allowed_elements:
                    if ttype == "StartTag":
                        strip_depth += 1
                    continue

                # Filter attributes.
                attrs = token.get("data", {})
                safe_attrs: Dict[str, str] = {}
                for k, v in attrs.items():
                    if k not in self.allowed_attrs:
                        continue
                    if k in _URI_ATTRS:
                        scheme = v.split(":", 1)[0].lower().strip() if ":" in v else ""
                        if scheme and scheme not in _SAFE_SCHEMES:
                            continue
                    safe_attrs[k] = v

                token = dict(token)
                token["data"] = safe_attrs
                yield token

            elif ttype == "EndTag":
                if strip_depth > 0:
                    strip_depth -= 1
                    continue
                name = token["name"]
                if name not in self.allowed_elements:
                    continue
                yield token

            elif ttype in ("Characters", "SpaceCharacters", "Comment", "Doctype"):
                if strip_depth == 0:
                    yield token
            else:
                yield token
