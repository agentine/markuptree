"""TreeWalker for xml.etree.ElementTree trees."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, Iterator, Optional

from markuptree.constants import voidElements
from markuptree.treewalkers.base import TreeWalker as BaseTreeWalker


_RE_TAG = re.compile(r"\{([^}]*)\}(.*)")


def _tag_parts(tag: str) -> tuple[Optional[str], str]:
    """Split an ET tag like ``{ns}name`` into ``(ns, name)``."""
    m = _RE_TAG.match(tag)
    if m:
        return m.group(1), m.group(2)
    return None, tag


class TreeWalker(BaseTreeWalker):
    """Walk an xml.etree.ElementTree and yield serializer tokens."""

    def __init__(self, tree: Any) -> None:
        if isinstance(tree, ET.ElementTree):
            tree = tree.getroot()
        super().__init__(tree)

    def __iter__(self) -> Iterator[Dict[str, Any]]:
        yield from self._walk(self.tree)

    def _walk(self, element: ET.Element) -> Iterator[Dict[str, Any]]:
        # Handle comment/PI nodes.
        if callable(element.tag):
            # ET.Comment produces a tag function.
            if element.tag == ET.Comment:  # type: ignore[comparison-overlap]
                yield from self.comment(element.text or "")
            else:
                yield from self.unknown(str(element.tag))
            # Comments can have tails too.
            if element.tail:
                yield from self.text(element.tail)
            return

        namespace, name = _tag_parts(element.tag)
        attrs: Dict[str, str] = dict(element.attrib)

        if name in voidElements:
            yield from self.emptyTag(namespace, name, attrs, len(element) > 0)
        else:
            yield from self.startTag(namespace, name, attrs)
            # Element text (before first child).
            if element.text:
                yield from self.text(element.text)
            # Walk children.
            for child in element:
                yield from self._walk(child)
            yield from self.endTag(namespace, name)

        # Tail text (text after this element, belongs to parent).
        if element.tail:
            yield from self.text(element.tail)
