"""Base TreeWalker class for markuptree."""

from __future__ import annotations

from typing import Any, Dict, Iterator, Optional

from markuptree.constants import namespaces, spaceCharacters, voidElements


_HTML_NS = namespaces["html"]

UNKNOWN = object()


class TreeWalker:
    """Base tree walker that yields serializer tokens from a parsed tree.

    Subclasses must implement ``__iter__`` to walk the specific tree
    format and yield tokens via the helper methods below.
    """

    def __init__(self, tree: Any) -> None:
        self.tree = tree

    def __iter__(self) -> Iterator[Dict[str, Any]]:
        raise NotImplementedError

    def error(self, msg: str) -> Dict[str, Any]:
        return {"type": "SerializeError", "data": msg}

    def emptyTag(
        self,
        namespace: Optional[str],
        name: str,
        attrs: Dict[str, str],
        hasChildren: bool = False,
    ) -> Iterator[Dict[str, Any]]:
        yield {
            "type": "EmptyTag",
            "namespace": namespace,
            "name": name,
            "data": attrs,
        }
        if hasChildren:
            yield self.error(f"Void element has children: <{name}>")

    def startTag(
        self,
        namespace: Optional[str],
        name: str,
        attrs: Dict[str, str],
    ) -> Iterator[Dict[str, Any]]:
        yield {
            "type": "StartTag",
            "namespace": namespace,
            "name": name,
            "data": attrs,
        }

    def endTag(
        self, namespace: Optional[str], name: str
    ) -> Iterator[Dict[str, Any]]:
        yield {
            "type": "EndTag",
            "namespace": namespace,
            "name": name,
        }

    def text(self, data: str) -> Iterator[Dict[str, Any]]:
        if not data:
            return
        if all(c in spaceCharacters for c in data):
            yield {"type": "SpaceCharacters", "data": data}
        else:
            yield {"type": "Characters", "data": data}

    def comment(self, data: str) -> Iterator[Dict[str, Any]]:
        yield {"type": "Comment", "data": data}

    def doctype(
        self,
        name: str,
        publicId: str = "",
        systemId: str = "",
    ) -> Iterator[Dict[str, Any]]:
        yield {
            "type": "Doctype",
            "name": name,
            "publicId": publicId,
            "systemId": systemId,
        }

    def entity(self, name: str) -> Iterator[Dict[str, Any]]:
        yield {"type": "Entity", "name": name}

    def unknown(self, nodeType: str) -> Iterator[Dict[str, Any]]:
        yield self.error(f"Unknown node type: {nodeType}")


class NonRecursiveTreeWalker(TreeWalker):
    """A tree walker that uses an explicit stack instead of recursion."""

    def getNodeDetails(self, node: Any) -> tuple:
        """Return node details as a tuple.

        Must be overridden. Returns one of:
        - (1, namespace, name, attrs, hasChildren)  # Element
        - (2, data)                                  # Text
        - (3, name, publicId, systemId)               # DocumentType
        - (4, data)                                  # Comment
        - (5, )                                       # Document
        - (6, )                                       # Fragment
        """
        raise NotImplementedError

    def getFirstChild(self, node: Any) -> Any:
        raise NotImplementedError

    def getNextSibling(self, node: Any) -> Any:
        raise NotImplementedError

    def getParentNode(self, node: Any) -> Any:
        raise NotImplementedError

    def __iter__(self) -> Iterator[Dict[str, Any]]:
        currentNode = self.tree
        while currentNode is not None:
            details = self.getNodeDetails(currentNode)
            kind = details[0]

            if kind == 1:  # Element
                _, namespace, name, attrs, hasChildren = details
                if name in voidElements:
                    yield from self.emptyTag(namespace, name, attrs, hasChildren)
                else:
                    yield from self.startTag(namespace, name, attrs)
                    if hasChildren:
                        firstChild = self.getFirstChild(currentNode)
                        if firstChild is not None:
                            currentNode = firstChild
                            continue
                    yield from self.endTag(namespace, name)
            elif kind == 2:  # Text
                yield from self.text(details[1])
            elif kind == 3:  # DocumentType
                yield from self.doctype(details[1], details[2], details[3])
            elif kind == 4:  # Comment
                yield from self.comment(details[1])
            elif kind in (5, 6):  # Document or Fragment
                firstChild = self.getFirstChild(currentNode)
                if firstChild is not None:
                    currentNode = firstChild
                    continue
            else:
                yield from self.unknown(str(kind))

            # Move to next sibling or back up the tree.
            while currentNode is not None:
                nextSibling = self.getNextSibling(currentNode)
                if nextSibling is not None:
                    currentNode = nextSibling
                    break
                currentNode = self.getParentNode(currentNode)
                if currentNode is None:
                    break
                details = self.getNodeDetails(currentNode)
                if details[0] == 1:  # Element
                    yield from self.endTag(details[1], details[2])
            else:
                currentNode = None
