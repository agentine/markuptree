"""Base TreeBuilder — HTML5 tree construction algorithm.

This module provides the abstract TreeBuilder base class that concrete
backends (etree, dom) subclass.  It also contains the full HTML5 tree
construction algorithm with all insertion modes.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from markuptree.constants import (
    formattingElements,
    headingElements,
    namespaces,
    scopingElements,
    specialElements,
    tableInsertModeElements,
    tokenTypes,
    voidElements,
)

# Marker used in the active formatting element list.
Marker = None

# Tags that trigger implied end tags.
_IMPLIED_END_TAGS = frozenset([
    "dd", "dt", "li", "optgroup", "option", "p", "rb", "rp", "rt", "rtc",
])

_IMPLIED_END_TAGS_THOROUGH = _IMPLIED_END_TAGS | frozenset([
    "caption", "colgroup", "tbody", "td", "tfoot", "th", "thead", "tr",
])

# List-item scope extras.
_LIST_SCOPE_EXTRA = frozenset([
    (namespaces["html"], "ol"),
    (namespaces["html"], "ul"),
])

# Button scope extras.
_BUTTON_SCOPE_EXTRA = frozenset([
    (namespaces["html"], "button"),
])

# Table scope elements.
_TABLE_SCOPE = frozenset([
    (namespaces["html"], "html"),
    (namespaces["html"], "table"),
    (namespaces["html"], "template"),
])

# Select scope: everything EXCEPT these is a scope boundary.
_SELECT_SCOPE_EXCLUDED = frozenset([
    "optgroup", "option",
])

_HTML_NS = namespaces["html"]


# ---------------------------------------------------------------------------
# Abstract Node interface
# ---------------------------------------------------------------------------

class Node:
    """Abstract tree node.  Concrete backends subclass this."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.parent: Optional[Node] = None
        self.namespace: Optional[str] = None
        self.attributes: Dict[str, str] = {}
        self.childNodes: List[Node] = []
        self._flags: List[str] = []

    def __str__(self) -> str:
        return f"<{self.name}>"

    def __repr__(self) -> str:
        return f"<Node {self.name}>"

    def appendChild(self, node: Node) -> None:
        raise NotImplementedError

    def insertText(self, data: str, insertBefore: Optional[Node] = None) -> None:
        raise NotImplementedError

    def insertBefore(self, node: Node, refNode: Node) -> None:
        raise NotImplementedError

    def removeChild(self, node: Node) -> None:
        raise NotImplementedError

    def reparentChildren(self, newParent: Node) -> None:
        raise NotImplementedError

    def cloneNode(self) -> Node:
        raise NotImplementedError

    def hasContent(self) -> bool:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Active Formatting Elements list
# ---------------------------------------------------------------------------

class ActiveFormattingElements(list):
    """List of active formatting elements with marker support."""

    def noahsArkCheck(self, node: Node) -> Optional[Node]:
        """Noah's Ark clause — if there are already 3 matching elements
        between the end of the list and the last marker, return the
        earliest one to be removed.
        """
        dominated = []
        for item in reversed(self):
            if item is Marker:
                break
            if (item.name == node.name
                    and item.namespace == node.namespace
                    and item.attributes == node.attributes):
                dominated.append(item)
        if len(dominated) >= 3:
            return dominated[-1]
        return None


# ---------------------------------------------------------------------------
# TreeBuilder
# ---------------------------------------------------------------------------

class TreeBuilder:
    """Abstract TreeBuilder base class implementing the HTML5 tree
    construction algorithm.

    Concrete backends (etree, dom) subclass and override the
    ``documentClass``, ``elementClass``, ``commentClass``,
    ``doctypeClass``, ``fragmentClass`` class attributes.
    """

    # Subclasses MUST set these.
    documentClass: Any = None
    elementClass: Any = None
    commentClass: Any = None
    doctypeClass: Any = None
    fragmentClass: Any = None

    # Implementation flag.
    implementationName: str = "base"

    def __init__(self, namespaceHTMLElements: bool = True) -> None:
        self.namespaceHTMLElements = namespaceHTMLElements
        self.defaultNamespace: Optional[str] = (
            _HTML_NS if namespaceHTMLElements else None
        )
        self.reset()

    # ------------------------------------------------------------------
    # Reset / setup
    # ------------------------------------------------------------------

    def reset(self) -> None:
        self.openElements: List[Node] = []
        self.activeFormattingElements = ActiveFormattingElements()
        self.headPointer: Optional[Node] = None
        self.formPointer: Optional[Node] = None
        self.document: Optional[Node] = None
        self.insertionMode: str = "initial"
        self.originalInsertionMode: Optional[str] = None
        self.templateInsertionModes: List[str] = []
        self.framesetOK = True
        self.tokenizer: Any = None
        self.fosterParenting = False
        self.pendingTableCharacters: List[str] = []
        self._parseErrors: List[str] = []

        if self.documentClass is not None:
            self.document = self.documentClass()

    # ------------------------------------------------------------------
    # Tree mutation helpers (called by insertion modes)
    # ------------------------------------------------------------------

    def elementInScope(
        self, target: str, variant: Optional[str] = None
    ) -> bool:
        """Check if *target* element name is in the appropriate scope."""
        scope_set = set(scopingElements)

        if variant == "listItem":
            scope_set |= _LIST_SCOPE_EXTRA
        elif variant == "button":
            scope_set |= _BUTTON_SCOPE_EXTRA
        elif variant == "table":
            scope_set = set(_TABLE_SCOPE)
        elif variant == "select":
            # Select scope: everything EXCEPT optgroup/option is a boundary.
            for node in reversed(self.openElements):
                if node.name == target and node.namespace == _HTML_NS:
                    return True
                if node.name not in _SELECT_SCOPE_EXCLUDED:
                    if node.namespace != _HTML_NS:
                        return False
                    return False
            return False

        for node in reversed(self.openElements):
            if node.name == target and node.namespace == _HTML_NS:
                return True
            if (node.namespace, node.name) in scope_set:
                return False
        return False

    def generateImpliedEndTags(self, exclude: Optional[str] = None) -> None:
        while (self.openElements
               and self.openElements[-1].name in _IMPLIED_END_TAGS
               and self.openElements[-1].name != exclude):
            self.openElements.pop()

    def generateImpliedEndTagsThoroughly(self) -> None:
        while (self.openElements
               and self.openElements[-1].name in _IMPLIED_END_TAGS_THOROUGH):
            self.openElements.pop()

    def getDocument(self) -> Any:
        return self.document

    def getFragment(self) -> Any:
        return self.document

    # ------------------------------------------------------------------
    # Element creation (backends override)
    # ------------------------------------------------------------------

    def createElement(self, token: Dict[str, Any]) -> Node:
        """Create an element from a start tag token."""
        name = token["name"]
        namespace = token.get("namespace", self.defaultNamespace)
        element = self.elementClass(name, namespace)
        element.attributes = dict(token.get("data", {}))
        return element

    def insertDoctype(self, token: Dict[str, Any]) -> None:
        name = token.get("name", "")
        publicId = token.get("publicId", "")
        systemId = token.get("systemId", "")
        doctype = self.doctypeClass(name, publicId, systemId)
        if self.document is not None:
            self.document.appendChild(doctype)

    def insertComment(self, token: Dict[str, Any], parent: Optional[Node] = None) -> None:
        if parent is None:
            parent = self.openElements[-1] if self.openElements else self.document
        if parent is not None:
            parent.appendChild(self.commentClass(token["data"]))

    def insertRoot(self, token: Dict[str, Any]) -> None:
        element = self.createElement(token)
        if self.document is not None:
            self.document.appendChild(element)
        self.openElements.append(element)

    def insertElement(self, token: Dict[str, Any]) -> Node:
        """Insert an element at the appropriate insertion position."""
        element = self.createElement(token)
        self._insertNode(element)
        self.openElements.append(element)
        return element

    def insertText(self, data: str) -> None:
        """Insert text at the appropriate insertion position."""
        parent, insertBefore = self._getInsertionPoint()
        if parent is not None:
            parent.insertText(data, insertBefore)

    def _insertNode(self, node: Node) -> None:
        parent, insertBefore = self._getInsertionPoint()
        if parent is not None:
            if insertBefore is not None:
                parent.insertBefore(node, insertBefore)
            else:
                parent.appendChild(node)

    def _getInsertionPoint(self) -> Tuple[Optional[Node], Optional[Node]]:
        """Return (parent, insertBefore) for the current insertion position.

        Handles foster parenting when we're inside a table.
        """
        if self.fosterParenting and self.openElements and self.openElements[-1].name in tableInsertModeElements:
            return self._getFosterParent()
        if self.openElements:
            return (self.openElements[-1], None)
        return (self.document, None)

    def _getFosterParent(self) -> Tuple[Optional[Node], Optional[Node]]:
        """Find the foster parent for misnested table content."""
        lastTable = None
        lastTableIdx = -1
        for i in range(len(self.openElements) - 1, -1, -1):
            if self.openElements[i].name == "table":
                lastTable = self.openElements[i]
                lastTableIdx = i
                break

        if lastTable is None:
            return (self.openElements[0], None)

        if lastTable.parent is not None:
            return (lastTable.parent, lastTable)

        # If table has no parent, insert before table in the stack.
        return (self.openElements[lastTableIdx - 1], None)

    # ------------------------------------------------------------------
    # Active formatting elements
    # ------------------------------------------------------------------

    def reconstructActiveFormattingElements(self) -> None:
        if not self.activeFormattingElements:
            return
        entry = self.activeFormattingElements[-1]
        if entry is Marker or entry in self.openElements:
            return

        i = len(self.activeFormattingElements) - 1
        while i > 0:
            i -= 1
            entry = self.activeFormattingElements[i]
            if entry is Marker or entry in self.openElements:
                i += 1
                break

        while i < len(self.activeFormattingElements):
            entry = self.activeFormattingElements[i]
            clone = entry.cloneNode()
            element = self.insertElement({
                "type": tokenTypes["StartTag"],
                "name": clone.name,
                "namespace": clone.namespace,
                "data": dict(clone.attributes),
            })
            self.activeFormattingElements[i] = element
            i += 1

    def clearActiveFormattingElements(self) -> None:
        """Clear the list back to the last marker."""
        while self.activeFormattingElements:
            item = self.activeFormattingElements.pop()
            if item is Marker:
                break

    # ------------------------------------------------------------------
    # Adoption agency algorithm
    # ------------------------------------------------------------------

    def _adoptionAgency(self, token: Dict[str, Any]) -> bool:
        """Run the adoption agency algorithm for the given end tag token.

        Returns True if the algorithm handled it, False if the caller
        should handle it as "any other end tag".
        """
        tag = token["name"]
        outer_limit = 8

        for _ in range(outer_limit):
            # Step 1: Find the formatting element.
            formattingElement = None
            feIdx = -1
            for i in range(len(self.activeFormattingElements) - 1, -1, -1):
                entry = self.activeFormattingElements[i]
                if entry is Marker:
                    break
                if entry.name == tag:
                    formattingElement = entry
                    feIdx = i
                    break

            if formattingElement is None:
                return False

            # Step 2: Check if formatting element is in the stack.
            try:
                feStackIdx = self.openElements.index(formattingElement)
            except ValueError:
                self._parseErrors.append("adoption-agency-missing-from-stack")
                self.activeFormattingElements.remove(formattingElement)
                return True

            # Step 3: Check scope.
            if not self.elementInScope(tag):
                self._parseErrors.append("adoption-agency-not-in-scope")
                return True

            # Step 4: If fe is not the current node, parse error.
            if formattingElement is not self.openElements[-1]:
                self._parseErrors.append("adoption-agency-1.3")

            # Step 5: Find the furthest block.
            furthestBlock = None
            fbIdx = -1
            for i in range(feStackIdx + 1, len(self.openElements)):
                el = self.openElements[i]
                if (el.namespace, el.name) in specialElements:
                    furthestBlock = el
                    fbIdx = i
                    break

            if furthestBlock is None:
                # Pop up to and including formatting element.
                while self.openElements[-1] is not formattingElement:
                    self.openElements.pop()
                self.openElements.pop()
                self.activeFormattingElements.remove(formattingElement)
                return True

            # Step 6: Common ancestor.
            commonAncestor = self.openElements[feStackIdx - 1]

            # Step 7: Bookmark.
            bookmark = feIdx

            # Step 8-13: Inner loop.
            node = furthestBlock
            lastNode = furthestBlock
            nodeIdx = fbIdx
            inner_limit = 3

            for innerCount in range(1, inner_limit + 1):
                nodeIdx -= 1
                if nodeIdx < 0:
                    break
                node = self.openElements[nodeIdx]

                if node not in self.activeFormattingElements:
                    self.openElements.remove(node)
                    nodeIdx -= 1
                    continue

                if node is formattingElement:
                    break

                # Replace in active formatting list and stack.
                clone = node.cloneNode()
                afIdx = self.activeFormattingElements.index(node)
                self.activeFormattingElements[afIdx] = clone
                self.openElements[nodeIdx] = clone
                node = clone

                if lastNode is furthestBlock:
                    bookmark = afIdx + 1

                if lastNode.parent is not None:
                    lastNode.parent.removeChild(lastNode)
                node.appendChild(lastNode)
                lastNode = node

            # Step 14: Insert last node into common ancestor.
            if lastNode.parent is not None:
                lastNode.parent.removeChild(lastNode)
            commonAncestor.appendChild(lastNode)

            # Step 15: Create element for formatting element.
            clone = formattingElement.cloneNode()

            # Step 16: Move children of furthest block to clone.
            furthestBlock.reparentChildren(clone)

            # Step 17: Insert clone into furthest block.
            furthestBlock.appendChild(clone)

            # Step 18: Fix up formatting element list.
            if formattingElement in self.activeFormattingElements:
                self.activeFormattingElements.remove(formattingElement)
            if bookmark < len(self.activeFormattingElements):
                self.activeFormattingElements.insert(bookmark, clone)
            else:
                self.activeFormattingElements.append(clone)

            # Step 19: Fix up open elements stack.
            if formattingElement in self.openElements:
                self.openElements.remove(formattingElement)
            insertIdx = self.openElements.index(furthestBlock) + 1
            self.openElements.insert(insertIdx, clone)

        return True

    # ------------------------------------------------------------------
    # Token dispatch
    # ------------------------------------------------------------------

    def processToken(self, token: Dict[str, Any]) -> None:
        """Process a single token through the tree construction algorithm."""
        ttype = token["type"]
        handler = getattr(self, f"_mode_{self.insertionMode}", None)
        if handler is None:
            raise RuntimeError(f"Unknown insertion mode: {self.insertionMode}")
        handler(token)

    # ------------------------------------------------------------------
    # Insertion modes
    # ------------------------------------------------------------------

    def _mode_initial(self, token: Dict[str, Any]) -> None:
        ttype = token["type"]
        if ttype == tokenTypes["SpaceCharacters"]:
            return
        if ttype == tokenTypes["Comment"]:
            self.insertComment(token, self.document)
            return
        if ttype == tokenTypes["Doctype"]:
            self.insertDoctype(token)
            self.insertionMode = "beforeHtml"
            return
        # Anything else → quirks mode, reprocess in beforeHtml.
        self._parseErrors.append("expected-doctype-but-got-" + str(ttype))
        self.insertionMode = "beforeHtml"
        self._mode_beforeHtml(token)

    def _mode_beforeHtml(self, token: Dict[str, Any]) -> None:
        ttype = token["type"]
        if ttype == tokenTypes["Doctype"]:
            self._parseErrors.append("unexpected-doctype")
            return
        if ttype == tokenTypes["Comment"]:
            self.insertComment(token, self.document)
            return
        if ttype == tokenTypes["SpaceCharacters"]:
            return
        if ttype == tokenTypes["StartTag"] and token["name"] == "html":
            self.insertRoot(token)
            self.insertionMode = "beforeHead"
            return
        if ttype == tokenTypes["EndTag"] and token["name"] not in ("head", "body", "html", "br"):
            self._parseErrors.append("unexpected-end-tag-before-html")
            return
        # Anything else: create html element, reprocess.
        self.insertRoot({"type": tokenTypes["StartTag"], "name": "html", "data": {}})
        self.insertionMode = "beforeHead"
        self._mode_beforeHead(token)

    def _mode_beforeHead(self, token: Dict[str, Any]) -> None:
        ttype = token["type"]
        if ttype == tokenTypes["SpaceCharacters"]:
            return
        if ttype == tokenTypes["Comment"]:
            self.insertComment(token)
            return
        if ttype == tokenTypes["Doctype"]:
            self._parseErrors.append("unexpected-doctype")
            return
        if ttype == tokenTypes["StartTag"]:
            name = token["name"]
            if name == "html":
                self._mode_inBody(token)
                return
            if name == "head":
                self.headPointer = self.insertElement(token)
                self.insertionMode = "inHead"
                return
        if ttype == tokenTypes["EndTag"] and token["name"] not in ("head", "body", "html", "br"):
            self._parseErrors.append("unexpected-end-tag-before-head")
            return
        # Anything else: insert head, reprocess.
        self.headPointer = self.insertElement(
            {"type": tokenTypes["StartTag"], "name": "head", "data": {}}
        )
        self.insertionMode = "inHead"
        self._mode_inHead(token)

    def _mode_inHead(self, token: Dict[str, Any]) -> None:
        ttype = token["type"]
        if ttype == tokenTypes["SpaceCharacters"]:
            self.insertText(token["data"])
            return
        if ttype == tokenTypes["Comment"]:
            self.insertComment(token)
            return
        if ttype == tokenTypes["Doctype"]:
            self._parseErrors.append("unexpected-doctype")
            return
        if ttype == tokenTypes["StartTag"]:
            name = token["name"]
            if name == "html":
                self._mode_inBody(token)
                return
            if name in ("base", "basefont", "bgsound", "link", "meta"):
                self.insertElement(token)
                self.openElements.pop()
                return
            if name == "title":
                self._parseRCDataRawtext(token, "RCDATA")
                return
            if name in ("noframes", "style"):
                self._parseRCDataRawtext(token, "RAWTEXT")
                return
            if name == "noscript":
                self.insertElement(token)
                self.insertionMode = "inHeadNoscript"
                return
            if name == "script":
                self._parseRCDataRawtext(token, "RAWTEXT")
                return
            if name == "template":
                self.insertElement(token)
                self.activeFormattingElements.append(Marker)
                self.framesetOK = False
                self.insertionMode = "inTemplate"
                self.templateInsertionModes.append("inTemplate")
                return
            if name == "head":
                self._parseErrors.append("unexpected-start-tag")
                return
        if ttype == tokenTypes["EndTag"]:
            name = token["name"]
            if name == "head":
                self.openElements.pop()
                self.insertionMode = "afterHead"
                return
            if name in ("body", "html", "br"):
                pass  # fall through to "anything else"
            elif name == "template":
                if "template" not in [el.name for el in self.openElements]:
                    self._parseErrors.append("unexpected-end-tag")
                    return
                self.generateImpliedEndTagsThoroughly()
                if self.openElements[-1].name != "template":
                    self._parseErrors.append("expected-closing-tag")
                while self.openElements:
                    el = self.openElements.pop()
                    if el.name == "template":
                        break
                self.clearActiveFormattingElements()
                if self.templateInsertionModes:
                    self.templateInsertionModes.pop()
                self._resetInsertionMode()
                return
            else:
                self._parseErrors.append("unexpected-end-tag")
                return
        # Anything else: pop head, reprocess in afterHead.
        self.openElements.pop()
        self.insertionMode = "afterHead"
        self._mode_afterHead(token)

    def _mode_inHeadNoscript(self, token: Dict[str, Any]) -> None:
        ttype = token["type"]
        if ttype == tokenTypes["Doctype"]:
            self._parseErrors.append("unexpected-doctype")
            return
        if ttype == tokenTypes["Comment"]:
            self._mode_inHead(token)
            return
        if ttype == tokenTypes["SpaceCharacters"]:
            self._mode_inHead(token)
            return
        if ttype == tokenTypes["StartTag"]:
            name = token["name"]
            if name == "html":
                self._mode_inBody(token)
                return
            if name in ("basefont", "bgsound", "link", "meta", "noframes", "style"):
                self._mode_inHead(token)
                return
            if name in ("head", "noscript"):
                self._parseErrors.append("unexpected-start-tag")
                return
        if ttype == tokenTypes["EndTag"]:
            name = token["name"]
            if name == "noscript":
                self.openElements.pop()
                self.insertionMode = "inHead"
                return
            if name != "br":
                self._parseErrors.append("unexpected-end-tag")
                return
        # Anything else.
        self._parseErrors.append("unexpected-token-in-head-noscript")
        self.openElements.pop()
        self.insertionMode = "inHead"
        self._mode_inHead(token)

    def _mode_afterHead(self, token: Dict[str, Any]) -> None:
        ttype = token["type"]
        if ttype == tokenTypes["SpaceCharacters"]:
            self.insertText(token["data"])
            return
        if ttype == tokenTypes["Comment"]:
            self.insertComment(token)
            return
        if ttype == tokenTypes["Doctype"]:
            self._parseErrors.append("unexpected-doctype")
            return
        if ttype == tokenTypes["StartTag"]:
            name = token["name"]
            if name == "html":
                self._mode_inBody(token)
                return
            if name == "body":
                self.insertElement(token)
                self.framesetOK = False
                self.insertionMode = "inBody"
                return
            if name == "frameset":
                self.insertElement(token)
                self.insertionMode = "inFrameset"
                return
            if name in (
                "base", "basefont", "bgsound", "link", "meta",
                "noframes", "script", "style", "template", "title",
            ):
                self._parseErrors.append("unexpected-start-tag")
                self.openElements.append(self.headPointer)
                self._mode_inHead(token)
                if self.headPointer in self.openElements:
                    self.openElements.remove(self.headPointer)
                return
            if name == "head":
                self._parseErrors.append("unexpected-start-tag")
                return
        if ttype == tokenTypes["EndTag"]:
            name = token["name"]
            if name in ("body", "html", "br"):
                pass  # fall through
            elif name == "template":
                self._mode_inHead(token)
                return
            else:
                self._parseErrors.append("unexpected-end-tag")
                return
        # Anything else: insert body, reprocess.
        self.insertElement(
            {"type": tokenTypes["StartTag"], "name": "body", "data": {}}
        )
        self.insertionMode = "inBody"
        self.framesetOK = True
        self._mode_inBody(token)

    # ------------------------------------------------------------------
    # inBody
    # ------------------------------------------------------------------

    def _mode_inBody(self, token: Dict[str, Any]) -> None:
        ttype = token["type"]

        if ttype == tokenTypes["Characters"]:
            self.reconstructActiveFormattingElements()
            self.insertText(token["data"])
            self.framesetOK = False
            return

        if ttype == tokenTypes["SpaceCharacters"]:
            self.reconstructActiveFormattingElements()
            self.insertText(token["data"])
            return

        if ttype == tokenTypes["Comment"]:
            self.insertComment(token)
            return

        if ttype == tokenTypes["Doctype"]:
            self._parseErrors.append("unexpected-doctype")
            return

        if ttype == tokenTypes["StartTag"]:
            self._startTagInBody(token)
            return

        if ttype == tokenTypes["EndTag"]:
            self._endTagInBody(token)
            return

        if ttype == tokenTypes["ParseError"]:
            self._parseErrors.append(token.get("data", "unknown"))
            return

    def _startTagInBody(self, token: Dict[str, Any]) -> None:
        name = token["name"]

        if name == "html":
            self._parseErrors.append("unexpected-start-tag")
            if self.openElements:
                for k, v in token.get("data", {}).items():
                    if k not in self.openElements[0].attributes:
                        self.openElements[0].attributes[k] = v
            return

        if name in (
            "base", "basefont", "bgsound", "link", "meta",
            "noframes", "script", "style", "template", "title",
        ):
            self._mode_inHead(token)
            return

        if name == "body":
            self._parseErrors.append("unexpected-start-tag")
            if (len(self.openElements) < 2
                    or self.openElements[1].name != "body"):
                return
            self.framesetOK = False
            for k, v in token.get("data", {}).items():
                if k not in self.openElements[1].attributes:
                    self.openElements[1].attributes[k] = v
            return

        if name == "frameset":
            self._parseErrors.append("unexpected-start-tag")
            if (not self.framesetOK
                    or len(self.openElements) < 2
                    or self.openElements[1].name != "body"):
                return
            body = self.openElements[1]
            if body.parent is not None:
                body.parent.removeChild(body)
            while len(self.openElements) > 1:
                self.openElements.pop()
            self.insertElement(token)
            self.insertionMode = "inFrameset"
            return

        if name in (
            "address", "article", "aside", "blockquote", "center",
            "details", "dialog", "dir", "div", "dl", "fieldset",
            "figcaption", "figure", "footer", "header", "hgroup",
            "main", "menu", "nav", "ol", "p", "search", "section",
            "summary", "ul",
        ):
            if self.elementInScope("p", variant="button"):
                self._closePElement()
            self.insertElement(token)
            return

        if name in headingElements:
            if self.elementInScope("p", variant="button"):
                self._closePElement()
            if self.openElements and self.openElements[-1].name in headingElements:
                self._parseErrors.append("unexpected-start-tag")
                self.openElements.pop()
            self.insertElement(token)
            return

        if name in ("pre", "listing"):
            if self.elementInScope("p", variant="button"):
                self._closePElement()
            self.insertElement(token)
            self.framesetOK = False
            return

        if name == "form":
            if self.formPointer is not None:
                self._parseErrors.append("unexpected-start-tag")
                return
            if self.elementInScope("p", variant="button"):
                self._closePElement()
            element = self.insertElement(token)
            self.formPointer = element
            return

        if name == "li":
            self.framesetOK = False
            for node in reversed(self.openElements):
                if node.name == "li":
                    self.generateImpliedEndTags(exclude="li")
                    if self.openElements[-1].name != "li":
                        self._parseErrors.append("unexpected-end-tag")
                    while self.openElements and self.openElements[-1].name != "li":
                        self.openElements.pop()
                    if self.openElements:
                        self.openElements.pop()
                    break
                if ((node.namespace, node.name) in specialElements
                        and node.name not in ("address", "div", "p")):
                    break
            if self.elementInScope("p", variant="button"):
                self._closePElement()
            self.insertElement(token)
            return

        if name in ("dd", "dt"):
            self.framesetOK = False
            for node in reversed(self.openElements):
                if node.name in ("dd", "dt"):
                    self.generateImpliedEndTags(exclude=node.name)
                    if self.openElements[-1].name != node.name:
                        self._parseErrors.append("unexpected-end-tag")
                    while self.openElements and self.openElements[-1].name not in ("dd", "dt"):
                        self.openElements.pop()
                    if self.openElements:
                        self.openElements.pop()
                    break
                if ((node.namespace, node.name) in specialElements
                        and node.name not in ("address", "div", "p")):
                    break
            if self.elementInScope("p", variant="button"):
                self._closePElement()
            self.insertElement(token)
            return

        if name == "plaintext":
            if self.elementInScope("p", variant="button"):
                self._closePElement()
            self.insertElement(token)
            return

        if name == "button":
            if self.elementInScope("button"):
                self._parseErrors.append("unexpected-start-tag")
                self.generateImpliedEndTags()
                while self.openElements and self.openElements[-1].name != "button":
                    self.openElements.pop()
                if self.openElements:
                    self.openElements.pop()
            self.reconstructActiveFormattingElements()
            self.insertElement(token)
            self.framesetOK = False
            return

        if name == "a":
            # Check if there's already an <a> in the active formatting list.
            for entry in reversed(self.activeFormattingElements):
                if entry is Marker:
                    break
                if entry.name == "a":
                    self._parseErrors.append("unexpected-start-tag-implies-end-tag")
                    self._adoptionAgency({"type": tokenTypes["EndTag"], "name": "a"})
                    if entry in self.activeFormattingElements:
                        self.activeFormattingElements.remove(entry)
                    if entry in self.openElements:
                        self.openElements.remove(entry)
                    break
            self.reconstructActiveFormattingElements()
            element = self.insertElement(token)
            self.activeFormattingElements.append(element)
            return

        if name in ("b", "big", "code", "em", "font", "i", "s",
                     "small", "strike", "strong", "tt", "u"):
            self.reconstructActiveFormattingElements()
            element = self.insertElement(token)
            self.activeFormattingElements.append(element)
            return

        if name == "nobr":
            self.reconstructActiveFormattingElements()
            if self.elementInScope("nobr"):
                self._parseErrors.append("unexpected-start-tag")
                self._adoptionAgency({"type": tokenTypes["EndTag"], "name": "nobr"})
                self.reconstructActiveFormattingElements()
            element = self.insertElement(token)
            self.activeFormattingElements.append(element)
            return

        if name in ("applet", "marquee", "object"):
            self.reconstructActiveFormattingElements()
            self.insertElement(token)
            self.activeFormattingElements.append(Marker)
            self.framesetOK = False
            return

        if name == "table":
            if self.elementInScope("p", variant="button"):
                self._closePElement()
            self.insertElement(token)
            self.framesetOK = False
            self.insertionMode = "inTable"
            return

        if name in ("area", "br", "embed", "img", "keygen", "wbr"):
            self.reconstructActiveFormattingElements()
            self.insertElement(token)
            self.openElements.pop()
            self.framesetOK = False
            return

        if name == "input":
            self.reconstructActiveFormattingElements()
            self.insertElement(token)
            self.openElements.pop()
            input_type = token.get("data", {}).get("type", "").lower()
            if input_type != "hidden":
                self.framesetOK = False
            return

        if name in ("param", "source", "track"):
            self.insertElement(token)
            self.openElements.pop()
            return

        if name == "hr":
            if self.elementInScope("p", variant="button"):
                self._closePElement()
            self.insertElement(token)
            self.openElements.pop()
            self.framesetOK = False
            return

        if name == "image":
            self._parseErrors.append("unexpected-start-tag-treated-as")
            token["name"] = "img"
            self._startTagInBody(token)
            return

        if name == "textarea":
            self.insertElement(token)
            if self.tokenizer is not None:
                self.tokenizer.state = "rcdata"
            self.framesetOK = False
            self.originalInsertionMode = self.insertionMode
            self.insertionMode = "text"
            return

        if name == "xmp":
            if self.elementInScope("p", variant="button"):
                self._closePElement()
            self.reconstructActiveFormattingElements()
            self.framesetOK = False
            self._parseRCDataRawtext(token, "RAWTEXT")
            return

        if name == "iframe":
            self.framesetOK = False
            self._parseRCDataRawtext(token, "RAWTEXT")
            return

        if name in ("noembed", "noframes"):
            self._parseRCDataRawtext(token, "RAWTEXT")
            return

        if name == "select":
            self.reconstructActiveFormattingElements()
            self.insertElement(token)
            self.framesetOK = False
            if self.insertionMode in ("inTable", "inCaption", "inTableBody",
                                       "inRow", "inCell"):
                self.insertionMode = "inSelectInTable"
            else:
                self.insertionMode = "inSelect"
            return

        if name in ("optgroup", "option"):
            if self.openElements and self.openElements[-1].name == "option":
                self.openElements.pop()
            self.reconstructActiveFormattingElements()
            self.insertElement(token)
            return

        if name in ("rb", "rtc"):
            if self.elementInScope("ruby"):
                self.generateImpliedEndTags()
            self.insertElement(token)
            return

        if name in ("rp", "rt"):
            if self.elementInScope("ruby"):
                self.generateImpliedEndTags(exclude="rtc")
            self.insertElement(token)
            return

        # Any other start tag.
        self.reconstructActiveFormattingElements()
        self.insertElement(token)

    def _endTagInBody(self, token: Dict[str, Any]) -> None:
        name = token["name"]

        if name == "body":
            if not self.elementInScope("body"):
                self._parseErrors.append("unexpected-end-tag")
                return
            self.insertionMode = "afterBody"
            return

        if name == "html":
            if not self.elementInScope("body"):
                self._parseErrors.append("unexpected-end-tag")
                return
            self.insertionMode = "afterBody"
            self._mode_afterBody(token)
            return

        if name in (
            "address", "article", "aside", "blockquote", "button",
            "center", "details", "dialog", "dir", "div", "dl",
            "fieldset", "figcaption", "figure", "footer", "header",
            "hgroup", "listing", "main", "menu", "nav", "ol", "pre",
            "search", "section", "summary", "ul",
        ):
            if not self.elementInScope(name):
                self._parseErrors.append("unexpected-end-tag")
                return
            self.generateImpliedEndTags()
            if self.openElements[-1].name != name:
                self._parseErrors.append("end-tag-too-early")
            while self.openElements:
                el = self.openElements.pop()
                if el.name == name:
                    break
            return

        if name == "form":
            node = self.formPointer
            self.formPointer = None
            if node is None or not self.elementInScope("form"):
                self._parseErrors.append("unexpected-end-tag")
                return
            self.generateImpliedEndTags()
            if self.openElements[-1] is not node:
                self._parseErrors.append("end-tag-too-early")
            if node in self.openElements:
                self.openElements.remove(node)
            return

        if name == "p":
            if not self.elementInScope("p", variant="button"):
                self._parseErrors.append("unexpected-end-tag")
                self.insertElement(
                    {"type": tokenTypes["StartTag"], "name": "p", "data": {}}
                )
            self._closePElement()
            return

        if name == "li":
            if not self.elementInScope("li", variant="listItem"):
                self._parseErrors.append("unexpected-end-tag")
                return
            self.generateImpliedEndTags(exclude="li")
            if self.openElements[-1].name != "li":
                self._parseErrors.append("end-tag-too-early")
            while self.openElements:
                el = self.openElements.pop()
                if el.name == "li":
                    break
            return

        if name in ("dd", "dt"):
            if not self.elementInScope(name):
                self._parseErrors.append("unexpected-end-tag")
                return
            self.generateImpliedEndTags(exclude=name)
            if self.openElements[-1].name != name:
                self._parseErrors.append("end-tag-too-early")
            while self.openElements:
                el = self.openElements.pop()
                if el.name == name:
                    break
            return

        if name in headingElements:
            found = False
            for h in headingElements:
                if self.elementInScope(h):
                    found = True
                    break
            if not found:
                self._parseErrors.append("unexpected-end-tag")
                return
            self.generateImpliedEndTags()
            if self.openElements[-1].name != name:
                self._parseErrors.append("end-tag-too-early")
            while self.openElements:
                el = self.openElements.pop()
                if el.name in headingElements:
                    break
            return

        if name in ("a", "b", "big", "code", "em", "font", "i", "nobr",
                     "s", "small", "strike", "strong", "tt", "u"):
            self._adoptionAgency(token)
            return

        if name in ("applet", "marquee", "object"):
            if not self.elementInScope(name):
                self._parseErrors.append("unexpected-end-tag")
                return
            self.generateImpliedEndTags()
            if self.openElements[-1].name != name:
                self._parseErrors.append("end-tag-too-early")
            while self.openElements:
                el = self.openElements.pop()
                if el.name == name:
                    break
            self.clearActiveFormattingElements()
            return

        if name == "br":
            self._parseErrors.append("unexpected-end-tag-treated-as")
            self.reconstructActiveFormattingElements()
            self.insertElement(
                {"type": tokenTypes["StartTag"], "name": "br", "data": {}}
            )
            self.openElements.pop()
            self.framesetOK = False
            return

        if name == "template":
            self._mode_inHead(token)
            return

        # Any other end tag.
        self._anyOtherEndTagInBody(token)

    def _anyOtherEndTagInBody(self, token: Dict[str, Any]) -> None:
        name = token["name"]
        for i in range(len(self.openElements) - 1, -1, -1):
            node = self.openElements[i]
            if node.name == name:
                self.generateImpliedEndTags(exclude=name)
                if self.openElements[-1].name != name:
                    self._parseErrors.append("unexpected-end-tag")
                while len(self.openElements) > i:
                    self.openElements.pop()
                break
            if (node.namespace, node.name) in specialElements:
                self._parseErrors.append("unexpected-end-tag")
                break

    def _closePElement(self) -> None:
        self.generateImpliedEndTags(exclude="p")
        if self.openElements and self.openElements[-1].name != "p":
            self._parseErrors.append("unexpected-end-tag")
        while self.openElements and self.openElements[-1].name != "p":
            self.openElements.pop()
        if self.openElements:
            self.openElements.pop()

    # ------------------------------------------------------------------
    # text mode
    # ------------------------------------------------------------------

    def _mode_text(self, token: Dict[str, Any]) -> None:
        ttype = token["type"]
        if ttype in (tokenTypes["Characters"], tokenTypes["SpaceCharacters"]):
            self.insertText(token["data"])
            return
        if ttype == tokenTypes["EndTag"]:
            self.openElements.pop()
            self.insertionMode = self.originalInsertionMode
            return
        # EOF
        self._parseErrors.append("expected-closing-tag-but-got-eof")
        self.openElements.pop()
        self.insertionMode = self.originalInsertionMode
        self.processToken(token)

    # ------------------------------------------------------------------
    # Table modes
    # ------------------------------------------------------------------

    def _mode_inTable(self, token: Dict[str, Any]) -> None:
        ttype = token["type"]
        if ttype in (tokenTypes["Characters"], tokenTypes["SpaceCharacters"]):
            if self.openElements and self.openElements[-1].name in ("table", "tbody", "tfoot", "thead", "tr"):
                self.pendingTableCharacters = []
                self.originalInsertionMode = self.insertionMode
                self.insertionMode = "inTableText"
                self._mode_inTableText(token)
                return
        if ttype == tokenTypes["Comment"]:
            self.insertComment(token)
            return
        if ttype == tokenTypes["Doctype"]:
            self._parseErrors.append("unexpected-doctype")
            return
        if ttype == tokenTypes["StartTag"]:
            name = token["name"]
            if name == "caption":
                self._clearStackBackToTableContext()
                self.activeFormattingElements.append(Marker)
                self.insertElement(token)
                self.insertionMode = "inCaption"
                return
            if name == "colgroup":
                self._clearStackBackToTableContext()
                self.insertElement(token)
                self.insertionMode = "inColumnGroup"
                return
            if name == "col":
                self._clearStackBackToTableContext()
                self.insertElement(
                    {"type": tokenTypes["StartTag"], "name": "colgroup", "data": {}}
                )
                self.insertionMode = "inColumnGroup"
                self._mode_inColumnGroup(token)
                return
            if name in ("tbody", "tfoot", "thead"):
                self._clearStackBackToTableContext()
                self.insertElement(token)
                self.insertionMode = "inTableBody"
                return
            if name in ("td", "th", "tr"):
                self._clearStackBackToTableContext()
                self.insertElement(
                    {"type": tokenTypes["StartTag"], "name": "tbody", "data": {}}
                )
                self.insertionMode = "inTableBody"
                self._mode_inTableBody(token)
                return
            if name == "table":
                self._parseErrors.append("unexpected-start-tag-implies-end-tag")
                if self.elementInScope("table", variant="table"):
                    while self.openElements:
                        el = self.openElements.pop()
                        if el.name == "table":
                            break
                    self._resetInsertionMode()
                    self.processToken(token)
                return
            if name in ("style", "script", "template"):
                self._mode_inHead(token)
                return
            if name == "input":
                if token.get("data", {}).get("type", "").lower() == "hidden":
                    self._parseErrors.append("unexpected-hidden-input")
                    self.insertElement(token)
                    self.openElements.pop()
                    return
                else:
                    self._parseErrors.append("unexpected-start-tag")
                    self._inTableFosterParenting(token)
                    return
            if name == "form":
                self._parseErrors.append("unexpected-start-tag")
                if self.formPointer is not None:
                    return
                self.formPointer = self.insertElement(token)
                self.openElements.pop()
                return
        if ttype == tokenTypes["EndTag"]:
            name = token["name"]
            if name == "table":
                if not self.elementInScope("table", variant="table"):
                    self._parseErrors.append("unexpected-end-tag")
                    return
                while self.openElements:
                    el = self.openElements.pop()
                    if el.name == "table":
                        break
                self._resetInsertionMode()
                return
            if name in ("body", "caption", "col", "colgroup", "html",
                        "tbody", "td", "tfoot", "th", "thead", "tr"):
                self._parseErrors.append("unexpected-end-tag")
                return
            if name == "template":
                self._mode_inHead(token)
                return
        # Anything else: foster parenting.
        self._parseErrors.append("unexpected-token-in-table")
        self._inTableFosterParenting(token)

    def _inTableFosterParenting(self, token: Dict[str, Any]) -> None:
        self.fosterParenting = True
        self._mode_inBody(token)
        self.fosterParenting = False

    def _clearStackBackToTableContext(self) -> None:
        while self.openElements and self.openElements[-1].name not in ("table", "template", "html"):
            self.openElements.pop()

    def _mode_inTableText(self, token: Dict[str, Any]) -> None:
        ttype = token["type"]
        if ttype in (tokenTypes["Characters"], tokenTypes["SpaceCharacters"]):
            self.pendingTableCharacters.append(token["data"])
            return
        # Flush pending characters.
        combined = "".join(self.pendingTableCharacters)
        if any(c not in "\t\n\u000C \r" for c in combined):
            # Non-space chars → foster parent them.
            self._parseErrors.append("unexpected-chars-in-table")
            self.fosterParenting = True
            self.insertText(combined)
            self.fosterParenting = False
        elif combined:
            self.insertText(combined)
        self.insertionMode = self.originalInsertionMode
        self.processToken(token)

    def _mode_inCaption(self, token: Dict[str, Any]) -> None:
        ttype = token["type"]
        if ttype == tokenTypes["EndTag"] and token["name"] == "caption":
            if not self.elementInScope("caption"):
                self._parseErrors.append("unexpected-end-tag")
                return
            self.generateImpliedEndTags()
            if self.openElements[-1].name != "caption":
                self._parseErrors.append("end-tag-too-early")
            while self.openElements:
                el = self.openElements.pop()
                if el.name == "caption":
                    break
            self.clearActiveFormattingElements()
            self.insertionMode = "inTable"
            return
        if ttype == tokenTypes["StartTag"] and token["name"] in (
            "caption", "col", "colgroup", "tbody", "td", "tfoot", "th", "thead", "tr",
        ):
            if not self.elementInScope("caption"):
                self._parseErrors.append("unexpected-start-tag")
                return
            self.generateImpliedEndTags()
            while self.openElements:
                el = self.openElements.pop()
                if el.name == "caption":
                    break
            self.clearActiveFormattingElements()
            self.insertionMode = "inTable"
            self.processToken(token)
            return
        if ttype == tokenTypes["EndTag"] and token["name"] == "table":
            if not self.elementInScope("caption"):
                self._parseErrors.append("unexpected-end-tag")
                return
            self.generateImpliedEndTags()
            while self.openElements:
                el = self.openElements.pop()
                if el.name == "caption":
                    break
            self.clearActiveFormattingElements()
            self.insertionMode = "inTable"
            self.processToken(token)
            return
        if ttype == tokenTypes["EndTag"] and token["name"] in (
            "body", "col", "colgroup", "html", "tbody", "td",
            "tfoot", "th", "thead", "tr",
        ):
            self._parseErrors.append("unexpected-end-tag")
            return
        # Anything else → process as inBody.
        self._mode_inBody(token)

    def _mode_inColumnGroup(self, token: Dict[str, Any]) -> None:
        ttype = token["type"]
        if ttype == tokenTypes["SpaceCharacters"]:
            self.insertText(token["data"])
            return
        if ttype == tokenTypes["Comment"]:
            self.insertComment(token)
            return
        if ttype == tokenTypes["Doctype"]:
            self._parseErrors.append("unexpected-doctype")
            return
        if ttype == tokenTypes["StartTag"]:
            name = token["name"]
            if name == "html":
                self._mode_inBody(token)
                return
            if name == "col":
                self.insertElement(token)
                self.openElements.pop()
                return
            if name == "template":
                self._mode_inHead(token)
                return
        if ttype == tokenTypes["EndTag"]:
            name = token["name"]
            if name == "colgroup":
                if self.openElements[-1].name != "colgroup":
                    self._parseErrors.append("unexpected-end-tag")
                    return
                self.openElements.pop()
                self.insertionMode = "inTable"
                return
            if name == "col":
                self._parseErrors.append("unexpected-end-tag")
                return
            if name == "template":
                self._mode_inHead(token)
                return
        # Anything else: pop colgroup, reprocess.
        if self.openElements and self.openElements[-1].name != "colgroup":
            self._parseErrors.append("unexpected-token")
            return
        self.openElements.pop()
        self.insertionMode = "inTable"
        self.processToken(token)

    def _mode_inTableBody(self, token: Dict[str, Any]) -> None:
        ttype = token["type"]
        if ttype == tokenTypes["StartTag"]:
            name = token["name"]
            if name == "tr":
                self._clearStackBackToTableBodyContext()
                self.insertElement(token)
                self.insertionMode = "inRow"
                return
            if name in ("th", "td"):
                self._parseErrors.append("unexpected-cell-in-table-body")
                self._clearStackBackToTableBodyContext()
                self.insertElement(
                    {"type": tokenTypes["StartTag"], "name": "tr", "data": {}}
                )
                self.insertionMode = "inRow"
                self._mode_inRow(token)
                return
            if name in ("caption", "col", "colgroup", "tbody", "tfoot", "thead"):
                if not self._tableBodyInScope():
                    self._parseErrors.append("unexpected-start-tag")
                    return
                self._clearStackBackToTableBodyContext()
                self.openElements.pop()
                self.insertionMode = "inTable"
                self.processToken(token)
                return
        if ttype == tokenTypes["EndTag"]:
            name = token["name"]
            if name in ("tbody", "tfoot", "thead"):
                if not self.elementInScope(name, variant="table"):
                    self._parseErrors.append("unexpected-end-tag")
                    return
                self._clearStackBackToTableBodyContext()
                self.openElements.pop()
                self.insertionMode = "inTable"
                return
            if name == "table":
                if not self._tableBodyInScope():
                    self._parseErrors.append("unexpected-end-tag")
                    return
                self._clearStackBackToTableBodyContext()
                self.openElements.pop()
                self.insertionMode = "inTable"
                self.processToken(token)
                return
            if name in ("body", "caption", "col", "colgroup", "html",
                        "td", "th", "tr"):
                self._parseErrors.append("unexpected-end-tag")
                return
        self._mode_inTable(token)

    def _tableBodyInScope(self) -> bool:
        for name in ("tbody", "tfoot", "thead"):
            if self.elementInScope(name, variant="table"):
                return True
        return False

    def _clearStackBackToTableBodyContext(self) -> None:
        while self.openElements and self.openElements[-1].name not in (
            "tbody", "tfoot", "thead", "template", "html"
        ):
            self.openElements.pop()

    def _mode_inRow(self, token: Dict[str, Any]) -> None:
        ttype = token["type"]
        if ttype == tokenTypes["StartTag"]:
            name = token["name"]
            if name in ("th", "td"):
                self._clearStackBackToTableRowContext()
                self.insertElement(token)
                self.insertionMode = "inCell"
                self.activeFormattingElements.append(Marker)
                return
            if name in ("caption", "col", "colgroup", "tbody", "tfoot",
                        "thead", "tr"):
                if not self.elementInScope("tr", variant="table"):
                    self._parseErrors.append("unexpected-start-tag")
                    return
                self._clearStackBackToTableRowContext()
                self.openElements.pop()
                self.insertionMode = "inTableBody"
                self.processToken(token)
                return
        if ttype == tokenTypes["EndTag"]:
            name = token["name"]
            if name == "tr":
                if not self.elementInScope("tr", variant="table"):
                    self._parseErrors.append("unexpected-end-tag")
                    return
                self._clearStackBackToTableRowContext()
                self.openElements.pop()
                self.insertionMode = "inTableBody"
                return
            if name == "table":
                if not self.elementInScope("tr", variant="table"):
                    self._parseErrors.append("unexpected-end-tag")
                    return
                self._clearStackBackToTableRowContext()
                self.openElements.pop()
                self.insertionMode = "inTableBody"
                self.processToken(token)
                return
            if name in ("tbody", "tfoot", "thead"):
                if not self.elementInScope(name, variant="table"):
                    self._parseErrors.append("unexpected-end-tag")
                    return
                if not self.elementInScope("tr", variant="table"):
                    return
                self._clearStackBackToTableRowContext()
                self.openElements.pop()
                self.insertionMode = "inTableBody"
                self.processToken(token)
                return
            if name in ("body", "caption", "col", "colgroup", "html",
                        "td", "th"):
                self._parseErrors.append("unexpected-end-tag")
                return
        self._mode_inTable(token)

    def _clearStackBackToTableRowContext(self) -> None:
        while self.openElements and self.openElements[-1].name not in (
            "tr", "template", "html"
        ):
            self.openElements.pop()

    def _mode_inCell(self, token: Dict[str, Any]) -> None:
        ttype = token["type"]
        if ttype == tokenTypes["EndTag"]:
            name = token["name"]
            if name in ("td", "th"):
                if not self.elementInScope(name):
                    self._parseErrors.append("unexpected-end-tag")
                    return
                self.generateImpliedEndTags()
                if self.openElements[-1].name != name:
                    self._parseErrors.append("end-tag-too-early")
                while self.openElements:
                    el = self.openElements.pop()
                    if el.name == name:
                        break
                self.clearActiveFormattingElements()
                self.insertionMode = "inRow"
                return
            if name in ("body", "caption", "col", "colgroup", "html"):
                self._parseErrors.append("unexpected-end-tag")
                return
            if name in ("table", "tbody", "tfoot", "thead", "tr"):
                if not self.elementInScope(name, variant="table"):
                    self._parseErrors.append("unexpected-end-tag")
                    return
                self._closeCell()
                self.processToken(token)
                return
        if ttype == tokenTypes["StartTag"]:
            name = token["name"]
            if name in ("caption", "col", "colgroup", "tbody", "td",
                        "tfoot", "th", "thead", "tr"):
                if (not self.elementInScope("td")
                        and not self.elementInScope("th")):
                    self._parseErrors.append("unexpected-start-tag")
                    return
                self._closeCell()
                self.processToken(token)
                return
        # Anything else → inBody.
        self._mode_inBody(token)

    def _closeCell(self) -> None:
        if self.elementInScope("td"):
            self.processToken({"type": tokenTypes["EndTag"], "name": "td"})
        elif self.elementInScope("th"):
            self.processToken({"type": tokenTypes["EndTag"], "name": "th"})

    # ------------------------------------------------------------------
    # Select modes
    # ------------------------------------------------------------------

    def _mode_inSelect(self, token: Dict[str, Any]) -> None:
        ttype = token["type"]
        if ttype in (tokenTypes["Characters"], tokenTypes["SpaceCharacters"]):
            self.insertText(token["data"])
            return
        if ttype == tokenTypes["Comment"]:
            self.insertComment(token)
            return
        if ttype == tokenTypes["Doctype"]:
            self._parseErrors.append("unexpected-doctype")
            return
        if ttype == tokenTypes["StartTag"]:
            name = token["name"]
            if name == "html":
                self._mode_inBody(token)
                return
            if name == "option":
                if self.openElements and self.openElements[-1].name == "option":
                    self.openElements.pop()
                self.insertElement(token)
                return
            if name == "optgroup":
                if self.openElements and self.openElements[-1].name == "option":
                    self.openElements.pop()
                if self.openElements and self.openElements[-1].name == "optgroup":
                    self.openElements.pop()
                self.insertElement(token)
                return
            if name == "select":
                self._parseErrors.append("unexpected-start-tag")
                if not self.elementInScope("select", variant="select"):
                    return
                while self.openElements:
                    el = self.openElements.pop()
                    if el.name == "select":
                        break
                self._resetInsertionMode()
                return
            if name in ("input", "keygen", "textarea"):
                self._parseErrors.append("unexpected-start-tag")
                if not self.elementInScope("select", variant="select"):
                    return
                while self.openElements:
                    el = self.openElements.pop()
                    if el.name == "select":
                        break
                self._resetInsertionMode()
                self.processToken(token)
                return
            if name in ("script", "template"):
                self._mode_inHead(token)
                return
        if ttype == tokenTypes["EndTag"]:
            name = token["name"]
            if name == "optgroup":
                if (self.openElements
                        and self.openElements[-1].name == "option"
                        and len(self.openElements) >= 2
                        and self.openElements[-2].name == "optgroup"):
                    self.openElements.pop()
                if self.openElements and self.openElements[-1].name == "optgroup":
                    self.openElements.pop()
                else:
                    self._parseErrors.append("unexpected-end-tag")
                return
            if name == "option":
                if self.openElements and self.openElements[-1].name == "option":
                    self.openElements.pop()
                else:
                    self._parseErrors.append("unexpected-end-tag")
                return
            if name == "select":
                if not self.elementInScope("select", variant="select"):
                    self._parseErrors.append("unexpected-end-tag")
                    return
                while self.openElements:
                    el = self.openElements.pop()
                    if el.name == "select":
                        break
                self._resetInsertionMode()
                return
            if name == "template":
                self._mode_inHead(token)
                return
        # Anything else: parse error, ignore.
        self._parseErrors.append("unexpected-token-in-select")

    def _mode_inSelectInTable(self, token: Dict[str, Any]) -> None:
        ttype = token["type"]
        if ttype == tokenTypes["StartTag"] and token["name"] in (
            "caption", "table", "tbody", "tfoot", "thead", "tr", "td", "th",
        ):
            self._parseErrors.append("unexpected-start-tag-in-select-in-table")
            while self.openElements and self.openElements[-1].name != "select":
                self.openElements.pop()
            if self.openElements:
                self.openElements.pop()
            self._resetInsertionMode()
            self.processToken(token)
            return
        if ttype == tokenTypes["EndTag"] and token["name"] in (
            "caption", "table", "tbody", "tfoot", "thead", "tr", "td", "th",
        ):
            self._parseErrors.append("unexpected-end-tag")
            if not self.elementInScope(token["name"], variant="table"):
                return
            while self.openElements and self.openElements[-1].name != "select":
                self.openElements.pop()
            if self.openElements:
                self.openElements.pop()
            self._resetInsertionMode()
            self.processToken(token)
            return
        self._mode_inSelect(token)

    # ------------------------------------------------------------------
    # Template mode
    # ------------------------------------------------------------------

    def _mode_inTemplate(self, token: Dict[str, Any]) -> None:
        ttype = token["type"]
        if ttype in (tokenTypes["Characters"], tokenTypes["SpaceCharacters"],
                     tokenTypes["Comment"], tokenTypes["Doctype"]):
            self._mode_inBody(token)
            return
        if ttype == tokenTypes["StartTag"]:
            name = token["name"]
            if name in ("base", "basefont", "bgsound", "link", "meta",
                        "noframes", "script", "style", "template", "title"):
                self._mode_inHead(token)
                return
            mode_map = {
                "caption": "inTable", "colgroup": "inColumnGroup",
                "col": "inColumnGroup", "tbody": "inTable",
                "tfoot": "inTable", "thead": "inTable",
                "tr": "inTableBody", "td": "inRow", "th": "inRow",
            }
            if name in mode_map:
                if self.templateInsertionModes:
                    self.templateInsertionModes[-1] = mode_map[name]
                self.insertionMode = mode_map[name]
                self.processToken(token)
                return
            if self.templateInsertionModes:
                self.templateInsertionModes[-1] = "inBody"
            self.insertionMode = "inBody"
            self.processToken(token)
            return
        if ttype == tokenTypes["EndTag"]:
            if token["name"] == "template":
                self._mode_inHead(token)
                return
            self._parseErrors.append("unexpected-end-tag")
            return
        # EOF
        if "template" not in [el.name for el in self.openElements]:
            return  # stop parsing
        self._parseErrors.append("eof-in-template")
        while self.openElements:
            el = self.openElements.pop()
            if el.name == "template":
                break
        self.clearActiveFormattingElements()
        if self.templateInsertionModes:
            self.templateInsertionModes.pop()
        self._resetInsertionMode()
        self.processToken(token)

    # ------------------------------------------------------------------
    # After body / frameset modes
    # ------------------------------------------------------------------

    def _mode_afterBody(self, token: Dict[str, Any]) -> None:
        ttype = token["type"]
        if ttype == tokenTypes["SpaceCharacters"]:
            self._mode_inBody(token)
            return
        if ttype == tokenTypes["Comment"]:
            # Insert as child of html element.
            self.insertComment(token, self.openElements[0] if self.openElements else self.document)
            return
        if ttype == tokenTypes["Doctype"]:
            self._parseErrors.append("unexpected-doctype")
            return
        if ttype == tokenTypes["StartTag"]:
            if token["name"] == "html":
                self._mode_inBody(token)
                return
            self._parseErrors.append("unexpected-start-tag-after-body")
            self.insertionMode = "inBody"
            self.processToken(token)
            return
        if ttype == tokenTypes["EndTag"]:
            if token["name"] == "html":
                self.insertionMode = "afterAfterBody"
                return
            self._parseErrors.append("unexpected-end-tag-after-body")
            self.insertionMode = "inBody"
            self.processToken(token)
            return
        # EOF: stop.

    def _mode_inFrameset(self, token: Dict[str, Any]) -> None:
        ttype = token["type"]
        if ttype == tokenTypes["SpaceCharacters"]:
            self.insertText(token["data"])
            return
        if ttype == tokenTypes["Comment"]:
            self.insertComment(token)
            return
        if ttype == tokenTypes["StartTag"]:
            name = token["name"]
            if name == "html":
                self._mode_inBody(token)
                return
            if name == "frameset":
                self.insertElement(token)
                return
            if name == "frame":
                self.insertElement(token)
                self.openElements.pop()
                return
            if name == "noframes":
                self._mode_inHead(token)
                return
        if ttype == tokenTypes["EndTag"] and token["name"] == "frameset":
            if self.openElements[-1].name == "html":
                self._parseErrors.append("unexpected-end-tag")
                return
            self.openElements.pop()
            self.insertionMode = "afterFrameset"
            return
        self._parseErrors.append("unexpected-token-in-frameset")

    def _mode_afterFrameset(self, token: Dict[str, Any]) -> None:
        ttype = token["type"]
        if ttype == tokenTypes["SpaceCharacters"]:
            self.insertText(token["data"])
            return
        if ttype == tokenTypes["Comment"]:
            self.insertComment(token)
            return
        if ttype == tokenTypes["StartTag"]:
            name = token["name"]
            if name == "html":
                self._mode_inBody(token)
                return
            if name == "noframes":
                self._mode_inHead(token)
                return
        if ttype == tokenTypes["EndTag"] and token["name"] == "html":
            self.insertionMode = "afterAfterFrameset"
            return
        self._parseErrors.append("unexpected-token-after-frameset")

    def _mode_afterAfterBody(self, token: Dict[str, Any]) -> None:
        ttype = token["type"]
        if ttype == tokenTypes["Comment"]:
            self.insertComment(token, self.document)
            return
        if ttype == tokenTypes["SpaceCharacters"]:
            self._mode_inBody(token)
            return
        if ttype == tokenTypes["Doctype"]:
            self._mode_inBody(token)
            return
        if ttype == tokenTypes["StartTag"] and token["name"] == "html":
            self._mode_inBody(token)
            return
        # EOF: stop.
        if ttype not in (tokenTypes["ParseError"],):
            self._parseErrors.append("unexpected-token-after-after-body")
            self.insertionMode = "inBody"
            self.processToken(token)

    def _mode_afterAfterFrameset(self, token: Dict[str, Any]) -> None:
        ttype = token["type"]
        if ttype == tokenTypes["Comment"]:
            self.insertComment(token, self.document)
            return
        if ttype == tokenTypes["SpaceCharacters"]:
            self._mode_inBody(token)
            return
        if ttype == tokenTypes["Doctype"]:
            self._mode_inBody(token)
            return
        if ttype == tokenTypes["StartTag"]:
            name = token["name"]
            if name == "html":
                self._mode_inBody(token)
                return
            if name == "noframes":
                self._mode_inHead(token)
                return
        # EOF: stop.
        self._parseErrors.append("unexpected-token-after-after-frameset")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resetInsertionMode(self) -> None:
        """Reset the insertion mode appropriately per the algorithm."""
        for i in range(len(self.openElements) - 1, -1, -1):
            node = self.openElements[i]
            last = (i == 0)
            name = node.name

            if name == "select":
                self.insertionMode = "inSelect"
                return
            if name in ("td", "th") and not last:
                self.insertionMode = "inCell"
                return
            if name == "tr":
                self.insertionMode = "inRow"
                return
            if name in ("tbody", "thead", "tfoot"):
                self.insertionMode = "inTableBody"
                return
            if name == "caption":
                self.insertionMode = "inCaption"
                return
            if name == "colgroup":
                self.insertionMode = "inColumnGroup"
                return
            if name == "table":
                self.insertionMode = "inTable"
                return
            if name == "template":
                self.insertionMode = (
                    self.templateInsertionModes[-1]
                    if self.templateInsertionModes
                    else "inTemplate"
                )
                return
            if name == "head" and not last:
                self.insertionMode = "inHead"
                return
            if name == "body":
                self.insertionMode = "inBody"
                return
            if name == "frameset":
                self.insertionMode = "inFrameset"
                return
            if name == "html":
                if self.headPointer is None:
                    self.insertionMode = "beforeHead"
                else:
                    self.insertionMode = "afterHead"
                return
            if last:
                self.insertionMode = "inBody"
                return

    def _parseRCDataRawtext(self, token: Dict[str, Any], content_type: str) -> None:
        """Handle RCDATA/RAWTEXT elements (title, style, script, etc.)."""
        self.insertElement(token)
        if self.tokenizer is not None:
            if content_type == "RCDATA":
                self.tokenizer.state = "rcdata"
            else:
                self.tokenizer.state = "rawtext"
        self.originalInsertionMode = self.insertionMode
        self.insertionMode = "text"
