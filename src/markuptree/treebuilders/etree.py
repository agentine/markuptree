"""TreeBuilder backend using xml.etree.ElementTree."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional

from markuptree.constants import namespaces
from markuptree.treebuilders.base import Node, TreeBuilder as BaseTreeBuilder

_HTML_NS = namespaces["html"]

# Tag prefix for namespace-aware elements.
def _tag(namespace: Optional[str], name: str) -> str:
    if namespace:
        return f"{{{namespace}}}{name}"
    return name


# ---------------------------------------------------------------------------
# Node wrappers around ET.Element / ET.SubElement
# ---------------------------------------------------------------------------

class Element(Node):
    """Wraps an ET.Element as a tree node."""

    def __init__(self, name: str, namespace: Optional[str] = None) -> None:
        super().__init__(name)
        self.namespace = namespace
        self._element = ET.Element(_tag(namespace, name))
        self.childNodes: List[Node] = []

    @property
    def _etree(self) -> ET.Element:
        return self._element

    def appendChild(self, node: Node) -> None:
        node.parent = self
        self.childNodes.append(node)
        if isinstance(node, Element):
            self._element.append(node._element)
        elif isinstance(node, TextNode):
            # Append text: use tail of last child or text of self.
            if len(self._element) > 0:
                last = self._element[-1]
                last.tail = (last.tail or "") + node.data
            else:
                self._element.text = (self._element.text or "") + node.data
        elif isinstance(node, Comment):
            comment_el = ET.Comment(node.comment_data)
            self._element.append(comment_el)
            node._element = comment_el

    def insertText(self, data: str, insertBefore: Optional[Node] = None) -> None:
        # Merge with existing text if possible.
        if self.childNodes and isinstance(self.childNodes[-1], TextNode):
            self.childNodes[-1].data += data
            # Update the underlying ET text.
            if len(self._element) > 0:
                last = self._element[-1]
                last.tail = (last.tail or "")[:-len(self.childNodes[-1].data) + len(self.childNodes[-1].data) - len(data)] + self.childNodes[-1].data
                # Simpler: just reconstruct tail
                last.tail = self.childNodes[-1].data if self.childNodes[-1]._is_tail else None
                if self.childNodes[-1]._is_tail:
                    last.tail = self.childNodes[-1].data
            else:
                self._element.text = self.childNodes[-1].data
            return
        text_node = TextNode(data)
        # Determine if this will be text or tail.
        if len(self._element) > 0:
            text_node._is_tail = True
            last = self._element[-1]
            last.tail = (last.tail or "") + data
        else:
            text_node._is_tail = False
            self._element.text = (self._element.text or "") + data
        text_node.parent = self
        self.childNodes.append(text_node)

    def insertBefore(self, node: Node, refNode: Node) -> None:
        idx = self.childNodes.index(refNode)
        node.parent = self
        self.childNodes.insert(idx, node)
        if isinstance(node, Element):
            # Find the position of refNode's element in ET.
            ref_idx = list(self._element).index(refNode._element) if isinstance(refNode, Element) else len(self._element)
            self._element.insert(ref_idx, node._element)

    def removeChild(self, node: Node) -> None:
        if node in self.childNodes:
            self.childNodes.remove(node)
        node.parent = None
        if isinstance(node, Element):
            try:
                self._element.remove(node._element)
            except ValueError:
                pass

    def reparentChildren(self, newParent: Node) -> None:
        for child in list(self.childNodes):
            self.removeChild(child)
            newParent.appendChild(child)

    def cloneNode(self) -> Element:
        clone = Element(self.name, self.namespace)
        clone.attributes = dict(self.attributes)
        for k, v in self.attributes.items():
            clone._element.set(k, v)
        return clone

    def hasContent(self) -> bool:
        return len(self.childNodes) > 0 or bool(self._element.text)


class TextNode(Node):
    """Represents a text node (stored as ET text/tail)."""

    def __init__(self, data: str) -> None:
        super().__init__("#text")
        self.data = data
        self._is_tail = False

    def appendChild(self, node: Node) -> None:
        pass  # text nodes have no children

    def insertText(self, data: str, insertBefore: Optional[Node] = None) -> None:
        self.data += data

    def insertBefore(self, node: Node, refNode: Node) -> None:
        pass

    def removeChild(self, node: Node) -> None:
        pass

    def reparentChildren(self, newParent: Node) -> None:
        pass

    def cloneNode(self) -> TextNode:
        return TextNode(self.data)

    def hasContent(self) -> bool:
        return bool(self.data)


class Comment(Node):
    """Comment node."""

    def __init__(self, data: str) -> None:
        super().__init__("#comment")
        self.comment_data = data
        self._element: Optional[ET.Element] = None

    def appendChild(self, node: Node) -> None:
        pass

    def insertText(self, data: str, insertBefore: Optional[Node] = None) -> None:
        pass

    def insertBefore(self, node: Node, refNode: Node) -> None:
        pass

    def removeChild(self, node: Node) -> None:
        pass

    def reparentChildren(self, newParent: Node) -> None:
        pass

    def cloneNode(self) -> Comment:
        return Comment(self.comment_data)

    def hasContent(self) -> bool:
        return bool(self.comment_data)


class DocumentType(Node):
    """DOCTYPE node."""

    def __init__(self, name: str, publicId: str = "", systemId: str = "") -> None:
        super().__init__("#doctype")
        self.doctype_name = name
        self.publicId = publicId
        self.systemId = systemId

    def appendChild(self, node: Node) -> None:
        pass

    def insertText(self, data: str, insertBefore: Optional[Node] = None) -> None:
        pass

    def insertBefore(self, node: Node, refNode: Node) -> None:
        pass

    def removeChild(self, node: Node) -> None:
        pass

    def reparentChildren(self, newParent: Node) -> None:
        pass

    def cloneNode(self) -> DocumentType:
        return DocumentType(self.doctype_name, self.publicId, self.systemId)

    def hasContent(self) -> bool:
        return bool(self.doctype_name)


class Document(Element):
    """Root document node wrapping the tree."""

    def __init__(self) -> None:
        super().__init__("#document")
        self._element = ET.Element("document")


class Fragment(Element):
    """Fragment container."""

    def __init__(self) -> None:
        super().__init__("#fragment")
        self._element = ET.Element("fragment")


# ---------------------------------------------------------------------------
# TreeBuilder
# ---------------------------------------------------------------------------

class TreeBuilder(BaseTreeBuilder):
    """TreeBuilder backend using xml.etree.ElementTree."""

    documentClass = Document
    commentClass = Comment
    doctypeClass = DocumentType
    fragmentClass = Fragment
    implementationName = "etree"

    @staticmethod
    def elementClass(name: str, namespace: Optional[str] = None) -> Element:
        return Element(name, namespace)

    def createElement(self, token: dict) -> Element:
        """Create an element and sync attributes to the underlying ET.Element."""
        name = token["name"]
        namespace = token.get("namespace", self.defaultNamespace)
        element = Element(name, namespace)
        attrs = dict(token.get("data", {}))
        element.attributes = attrs
        for k, v in attrs.items():
            element._element.set(k, v)
        return element

    def getDocument(self) -> ET.Element:
        """Return the root ET.Element of the parsed document."""
        if self.document is None:
            return ET.Element("html")
        # Find the html element.
        for child in self.document.childNodes:
            if isinstance(child, Element) and child.name == "html":
                return child._element
        return self.document._element

    def getFragment(self) -> list:
        """Return the children of the document as a list."""
        if self.document is None:
            return []
        result = []
        for child in self.document.childNodes:
            if isinstance(child, Element):
                result.append(child._element)
        return result
