"""TreeWalker for xml.dom.minidom trees."""

from __future__ import annotations

import xml.dom.minidom as minidom
from typing import Any, Dict, Iterator, Optional

from markuptree.constants import voidElements
from markuptree.treewalkers.base import TreeWalker as BaseTreeWalker


class TreeWalker(BaseTreeWalker):
    """Walk a minidom DOM tree and yield serializer tokens."""

    def __iter__(self) -> Iterator[Dict[str, Any]]:
        yield from self._walk(self.tree)

    def _walk(self, node: Any) -> Iterator[Dict[str, Any]]:
        if node.nodeType == node.DOCUMENT_NODE:
            for child in node.childNodes:
                yield from self._walk(child)

        elif node.nodeType == node.DOCUMENT_TYPE_NODE:
            yield from self.doctype(
                node.name or "",
                node.publicId or "",
                node.systemId or "",
            )

        elif node.nodeType == node.COMMENT_NODE:
            yield from self.comment(node.data or "")

        elif node.nodeType == node.TEXT_NODE:
            yield from self.text(node.data or "")

        elif node.nodeType == node.ELEMENT_NODE:
            namespace = node.namespaceURI
            name = node.localName or node.nodeName

            attrs: Dict[str, str] = {}
            if node.attributes:
                for i in range(node.attributes.length):
                    attr = node.attributes.item(i)
                    attrs[attr.name] = attr.value

            if name in voidElements:
                yield from self.emptyTag(
                    namespace, name, attrs, node.hasChildNodes()
                )
            else:
                yield from self.startTag(namespace, name, attrs)
                for child in node.childNodes:
                    yield from self._walk(child)
                yield from self.endTag(namespace, name)
        else:
            yield from self.unknown(str(node.nodeType))
