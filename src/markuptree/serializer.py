"""HTML serializer for markuptree."""

from __future__ import annotations

import re
from typing import Any, Dict, Iterator, Optional

from markuptree.constants import (
    booleanAttributes,
    namespaces,
    prefixes,
    spaceCharacters,
    voidElements,
)

_HTML_NS = namespaces["html"]

# Characters that must be escaped in text content.
_AMP_RE = re.compile(r"&")
_LT_RE = re.compile(r"<")
_GT_RE = re.compile(r">")

# Characters that must be escaped in attribute values.
_ATTR_QUOT_RE = re.compile(r'"')
_ATTR_APOS_RE = re.compile(r"'")
_ATTR_AMP_RE = _AMP_RE

_INVISIBLE_CHARS = {
    "\u0009": "&#x0009;",
    "\u000A": "&#x000A;",
    "\u000B": "&#x000B;",
    "\u000C": "&#x000C;",
    "\u000D": "&#x000D;",
    "\u0020": "&#x0020;",
}


def _escape_text(s: str) -> str:
    s = _AMP_RE.sub("&amp;", s)
    s = _LT_RE.sub("&lt;", s)
    s = _GT_RE.sub("&gt;", s)
    return s


def _escape_attr(s: str, quote_char: str = '"') -> str:
    s = _AMP_RE.sub("&amp;", s)
    if quote_char == '"':
        s = _ATTR_QUOT_RE.sub("&quot;", s)
    else:
        s = _ATTR_APOS_RE.sub("&#39;", s)
    return s


class HTMLSerializer:
    """Serialize a token stream to HTML.

    Supports the same 14 options as html5lib's HTMLSerializer.
    """

    # Default option values.
    quote_attr_values: str = "legacy"
    quote_char: str = '"'
    use_best_quote_char: bool = True
    omit_optional_tags: bool = True
    minimize_boolean_attributes: bool = True
    use_trailing_solidus: bool = False
    space_before_trailing_solidus: bool = True
    escape_lt_in_attrs: bool = False
    escape_rcdata: bool = False
    resolve_entities: bool = True
    alphabetical_attributes: bool = False
    inject_meta_charset: bool = True
    strip_whitespace: bool = False
    sanitize: bool = False
    escape_invisible_characters: bool = False

    def __init__(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            if hasattr(self, k):
                setattr(self, k, v)
            else:
                raise TypeError(f"Unknown option: {k!r}")
        self.errors: list[str] = []

    def serialize(
        self, treewalker: Any, encoding: Optional[str] = None
    ) -> Iterator[str]:
        """Yield HTML string fragments from a treewalker token stream."""
        in_cdata = False
        self.errors = []

        for token in treewalker:
            ttype = token["type"]

            if ttype == "Doctype":
                doctype = "<!DOCTYPE"
                name = token.get("name")
                if name:
                    doctype += f" {name}"
                publicId = token.get("publicId", "")
                systemId = token.get("systemId", "")
                if publicId:
                    doctype += f' PUBLIC "{publicId}"'
                    if systemId:
                        doctype += f' "{systemId}"'
                elif systemId:
                    doctype += f' SYSTEM "{systemId}"'
                doctype += ">"
                yield doctype

            elif ttype in ("StartTag", "EmptyTag"):
                name = token["name"]
                namespace = token.get("namespace", _HTML_NS)
                attrs = token.get("data", {})
                in_cdata = name in ("script", "style")

                yield self._serialize_tag(name, namespace, attrs, ttype == "EmptyTag")

            elif ttype == "EndTag":
                name = token["name"]
                in_cdata = False
                yield f"</{name}>"

            elif ttype in ("Characters", "SpaceCharacters"):
                data = token["data"]
                if in_cdata:
                    yield data
                else:
                    yield _escape_text(data)

            elif ttype == "Comment":
                data = token.get("data", "")
                yield f"<!--{data}-->"

            elif ttype == "Entity":
                name = token["name"]
                if self.resolve_entities:
                    # Try to resolve; fallback to raw.
                    yield f"&{name};"
                else:
                    yield f"&{name};"

            elif ttype == "SerializeError":
                self.errors.append(token["data"])

    def _serialize_tag(
        self,
        name: str,
        namespace: Optional[str],
        attrs: Dict[str, str],
        is_void: bool,
    ) -> str:
        s = f"<{name}"

        attr_items = list(attrs.items())
        if self.alphabetical_attributes:
            attr_items.sort(key=lambda x: x[0])

        for attr_name, attr_value in attr_items:
            # Boolean attribute minimization.
            is_boolean = attr_name in booleanAttributes.get("", frozenset())
            if not is_boolean:
                is_boolean = attr_name in booleanAttributes.get(name, frozenset())

            if self.minimize_boolean_attributes and is_boolean and (
                attr_value == "" or attr_value.lower() == attr_name.lower()
            ):
                s += f" {attr_name}"
            else:
                quote_char = self.quote_char
                if self.use_best_quote_char:
                    if '"' in attr_value and "'" not in attr_value:
                        quote_char = "'"
                    else:
                        quote_char = '"'

                attr_value_escaped = _escape_attr(attr_value, quote_char)
                if self.escape_lt_in_attrs:
                    attr_value_escaped = attr_value_escaped.replace("<", "&lt;")

                need_quotes = True
                if self.quote_attr_values == "legacy":
                    # Only quote when necessary.
                    if (
                        attr_value_escaped
                        and not any(
                            c in attr_value_escaped
                            for c in ('"', "'", "=", "<", ">", "`", " ", "\t", "\n", "\r", "\f")
                        )
                    ):
                        need_quotes = False
                elif self.quote_attr_values == "always":
                    need_quotes = True

                if need_quotes:
                    s += f" {attr_name}={quote_char}{attr_value_escaped}{quote_char}"
                else:
                    s += f" {attr_name}={attr_value_escaped}"

        if is_void and self.use_trailing_solidus:
            if self.space_before_trailing_solidus:
                s += " /"
            else:
                s += "/"

        s += ">"
        return s

    def render(
        self, treewalker: Any, encoding: Optional[str] = None
    ) -> str:
        """Serialize to a single string."""
        return "".join(self.serialize(treewalker, encoding))


def serialize(
    input: Any,
    tree: str = "etree",
    encoding: Optional[str] = None,
    **serializer_opts: Any,
) -> str:
    """Convenience function: walk a tree and serialize to HTML."""
    from markuptree.treewalkers import getTreeWalker

    Walker = getTreeWalker(tree)
    s = HTMLSerializer(**serializer_opts)
    return s.render(Walker(input), encoding)
