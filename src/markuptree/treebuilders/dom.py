"""TreeBuilder backend using xml.dom.minidom."""

from __future__ import annotations

import xml.dom.minidom as minidom
from typing import Any, Dict, List, Optional

from markuptree.constants import namespaces
from markuptree.treebuilders.base import Node, TreeBuilder as BaseTreeBuilder

_HTML_NS = namespaces["html"]


# ---------------------------------------------------------------------------
# Node wrappers around minidom nodes
# ---------------------------------------------------------------------------

class DomNode(Node):
    """Base wrapper for a minidom DOM node."""

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self._dom_node: Optional[Any] = None
        self.childNodes: List[Node] = []

    def appendChild(self, node: Node) -> None:
        node.parent = self
        self.childNodes.append(node)
        if hasattr(node, "_dom_node") and node._dom_node is not None and self._dom_node is not None:
            try:
                self._dom_node.appendChild(node._dom_node)
            except Exception:
                pass

    def insertText(self, data: str, insertBefore: Optional[Node] = None) -> None:
        if self.childNodes and isinstance(self.childNodes[-1], TextNode):
            self.childNodes[-1].data += data
            self.childNodes[-1]._dom_node.data = self.childNodes[-1].data
            return
        text_node = TextNode(data)
        if self._dom_node is not None:
            doc = self._dom_node.ownerDocument or self._dom_node
            text_node._dom_node = doc.createTextNode(data)
        self.appendChild(text_node)

    def insertBefore(self, node: Node, refNode: Node) -> None:
        idx = self.childNodes.index(refNode)
        node.parent = self
        self.childNodes.insert(idx, node)
        if (self._dom_node is not None
                and hasattr(node, "_dom_node") and node._dom_node is not None
                and hasattr(refNode, "_dom_node") and refNode._dom_node is not None):
            try:
                self._dom_node.insertBefore(node._dom_node, refNode._dom_node)
            except Exception:
                pass

    def removeChild(self, node: Node) -> None:
        if node in self.childNodes:
            self.childNodes.remove(node)
        node.parent = None
        if (self._dom_node is not None
                and hasattr(node, "_dom_node") and node._dom_node is not None):
            try:
                self._dom_node.removeChild(node._dom_node)
            except Exception:
                pass

    def reparentChildren(self, newParent: Node) -> None:
        for child in list(self.childNodes):
            self.removeChild(child)
            newParent.appendChild(child)

    def cloneNode(self) -> DomNode:
        clone = DomNode(self.name)
        clone.attributes = dict(self.attributes)
        return clone

    def hasContent(self) -> bool:
        return len(self.childNodes) > 0


class Element(DomNode):
    """Wraps a minidom Element."""

    def __init__(self, name: str, namespace: Optional[str] = None) -> None:
        super().__init__(name)
        self.namespace = namespace
        self._dom_node = None  # Set during insertion.

    def _ensure_dom(self, doc: minidom.Document) -> None:
        """Create the underlying minidom element if not yet created."""
        if self._dom_node is None:
            if self.namespace:
                self._dom_node = doc.createElementNS(self.namespace, self.name)
            else:
                self._dom_node = doc.createElement(self.name)
            for k, v in self.attributes.items():
                self._dom_node.setAttribute(k, v)

    def cloneNode(self) -> Element:
        clone = Element(self.name, self.namespace)
        clone.attributes = dict(self.attributes)
        return clone


class TextNode(DomNode):
    """Wraps a minidom Text node."""

    def __init__(self, data: str) -> None:
        super().__init__("#text")
        self.data = data
        self._dom_node = None

    def cloneNode(self) -> TextNode:
        return TextNode(self.data)

    def hasContent(self) -> bool:
        return bool(self.data)


class CommentNode(DomNode):
    """Wraps a minidom Comment."""

    def __init__(self, data: str) -> None:
        super().__init__("#comment")
        self.comment_data = data
        self._dom_node = None

    def cloneNode(self) -> CommentNode:
        return CommentNode(self.comment_data)


class DocumentTypeNode(DomNode):
    """DOCTYPE node."""

    def __init__(self, name: str, publicId: str = "", systemId: str = "") -> None:
        super().__init__("#doctype")
        self.doctype_name = name
        self.publicId = publicId
        self.systemId = systemId

    def cloneNode(self) -> DocumentTypeNode:
        return DocumentTypeNode(self.doctype_name, self.publicId, self.systemId)


class Document(DomNode):
    """Root document wrapping a minidom Document."""

    def __init__(self) -> None:
        super().__init__("#document")
        self._impl = minidom.getDOMImplementation()
        self._dom_node = self._impl.createDocument(None, None, None)

    def appendChild(self, node: Node) -> None:
        node.parent = self
        self.childNodes.append(node)
        if isinstance(node, Element):
            node._ensure_dom(self._dom_node)
            try:
                self._dom_node.appendChild(node._dom_node)
            except Exception:
                pass
        elif isinstance(node, DocumentTypeNode):
            # Create a proper doctype.
            try:
                dt = self._impl.createDocumentType(
                    node.doctype_name or "html",
                    node.publicId or "",
                    node.systemId or "",
                )
                node._dom_node = dt
                self._dom_node.appendChild(dt)
            except Exception:
                pass
        elif isinstance(node, CommentNode):
            node._dom_node = self._dom_node.createComment(node.comment_data)
            self._dom_node.appendChild(node._dom_node)

    def insertText(self, data: str, insertBefore: Optional[Node] = None) -> None:
        if self.childNodes and isinstance(self.childNodes[-1], TextNode):
            self.childNodes[-1].data += data
            if self.childNodes[-1]._dom_node:
                self.childNodes[-1]._dom_node.data = self.childNodes[-1].data
            return
        text_node = TextNode(data)
        text_node._dom_node = self._dom_node.createTextNode(data)
        self.appendChild(text_node)


class Fragment(DomNode):
    """Fragment container."""

    def __init__(self) -> None:
        super().__init__("#fragment")
        self._impl = minidom.getDOMImplementation()
        self._dom_node = self._impl.createDocument(None, None, None)


# ---------------------------------------------------------------------------
# TreeBuilder
# ---------------------------------------------------------------------------

class TreeBuilder(BaseTreeBuilder):
    """TreeBuilder backend using xml.dom.minidom."""

    documentClass = Document
    commentClass = CommentNode
    doctypeClass = DocumentTypeNode
    fragmentClass = Fragment
    implementationName = "dom"

    @staticmethod
    def elementClass(name: str, namespace: Optional[str] = None) -> Element:
        return Element(name, namespace)

    def createElement(self, token: dict) -> Element:
        """Create an element and ensure it has a DOM node."""
        name = token["name"]
        namespace = token.get("namespace", self.defaultNamespace)
        element = Element(name, namespace)
        element.attributes = dict(token.get("data", {}))
        # Eagerly create the DOM node.
        if self.document is not None and hasattr(self.document, "_dom_node"):
            element._ensure_dom(self.document._dom_node)
        return element

    def insertComment(self, token: dict, parent: Optional[Node] = None) -> None:
        if parent is None:
            parent = self.openElements[-1] if self.openElements else self.document
        if parent is not None:
            comment = CommentNode(token["data"])
            if hasattr(parent, "_dom_node") and parent._dom_node is not None:
                doc = parent._dom_node.ownerDocument or parent._dom_node
                comment._dom_node = doc.createComment(token["data"])
            parent.appendChild(comment)

    def getDocument(self) -> minidom.Document:
        """Return the minidom Document."""
        if self.document is not None and hasattr(self.document, "_dom_node"):
            return self.document._dom_node
        return minidom.Document()

    def getFragment(self) -> list:
        """Return children as a list."""
        if self.document is None:
            return []
        return [c for c in self.document.childNodes if isinstance(c, Element)]
