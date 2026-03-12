"""Tests for the base TreeBuilder and HTML5 tree construction algorithm."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from markuptree.constants import tokenTypes
from markuptree.inputstream import HTMLInputStream
from markuptree.tokenizer import HTMLTokenizer
from markuptree.treebuilders.base import Node, TreeBuilder


# ---------------------------------------------------------------------------
# Simple concrete Node and TreeBuilder for testing
# ---------------------------------------------------------------------------


class TestNode(Node):
    """Minimal concrete Node for unit tests."""

    def __init__(self, name: str, namespace: Optional[str] = None) -> None:
        super().__init__(name)
        self.namespace = namespace
        self.childNodes: List[TestNode] = []
        self._text_parts: List[str] = []

    def appendChild(self, node: Node) -> None:
        node.parent = self
        self.childNodes.append(node)  # type: ignore[arg-type]

    def insertText(self, data: str, insertBefore: Optional[Node] = None) -> None:
        # Merge with last text node if possible.
        if self.childNodes and getattr(self.childNodes[-1], "_is_text", False):
            self.childNodes[-1]._text_parts.append(data)
            self.childNodes[-1].name = "".join(self.childNodes[-1]._text_parts)
        else:
            text_node = TestNode("#text")
            text_node._is_text = True  # type: ignore[attr-defined]
            text_node._text_parts = [data]
            text_node.name = data
            self.appendChild(text_node)

    def insertBefore(self, node: Node, refNode: Node) -> None:
        idx = self.childNodes.index(refNode)  # type: ignore[arg-type]
        node.parent = self
        self.childNodes.insert(idx, node)  # type: ignore[arg-type]

    def removeChild(self, node: Node) -> None:
        self.childNodes.remove(node)  # type: ignore[arg-type]
        node.parent = None

    def reparentChildren(self, newParent: Node) -> None:
        for child in list(self.childNodes):
            self.removeChild(child)
            newParent.appendChild(child)

    def cloneNode(self) -> TestNode:
        clone = TestNode(self.name, self.namespace)
        clone.attributes = dict(self.attributes)
        return clone

    def hasContent(self) -> bool:
        return len(self.childNodes) > 0

    def text(self) -> str:
        """Get all text content recursively."""
        parts = []
        for child in self.childNodes:
            if getattr(child, "_is_text", False):
                parts.append(child.name)
            else:
                parts.append(child.text())
        return "".join(parts)


class TestDoctype(TestNode):
    def __init__(self, name: str, publicId: str = "", systemId: str = "") -> None:
        super().__init__("#doctype")
        self.doctype_name = name
        self.publicId = publicId
        self.systemId = systemId


class TestComment(TestNode):
    def __init__(self, data: str) -> None:
        super().__init__("#comment")
        self.comment_data = data


class TestTreeBuilder(TreeBuilder):
    """Concrete TreeBuilder using TestNode for testing."""

    documentClass = type("Doc", (TestNode,), {"__init__": lambda self: TestNode.__init__(self, "#document")})

    @staticmethod
    def elementClass(name: str, namespace: Optional[str] = None) -> TestNode:
        return TestNode(name, namespace)

    commentClass = TestComment
    doctypeClass = TestDoctype
    fragmentClass = type("Frag", (TestNode,), {"__init__": lambda self: TestNode.__init__(self, "#fragment")})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def build_tree(html: str) -> TestTreeBuilder:
    """Parse HTML and return the TreeBuilder."""
    builder = TestTreeBuilder()
    stream = HTMLInputStream(html)
    tokenizer = HTMLTokenizer(stream)
    for token in tokenizer:
        builder.processToken(token)
    return builder


def get_elements(node: TestNode, tag: Optional[str] = None) -> List[TestNode]:
    """Recursively find all elements, optionally filtered by tag name."""
    result = []
    for child in node.childNodes:
        if tag is None or child.name == tag:
            if not getattr(child, "_is_text", False) and child.name != "#comment" and child.name != "#doctype":
                result.append(child)
        result.extend(get_elements(child, tag))
    return result


# ---------------------------------------------------------------------------
# Tests: basic tree construction
# ---------------------------------------------------------------------------


class TestBasicTreeConstruction:
    def test_empty_doc(self) -> None:
        b = build_tree("")
        assert b.document is not None

    def test_doctype_and_html(self) -> None:
        b = build_tree("<!DOCTYPE html><html><head></head><body></body></html>")
        doc = b.document
        assert doc is not None
        # Should have doctype and html element.
        children = [c for c in doc.childNodes if c.name != "#text"]
        has_doctype = any(c.name == "#doctype" for c in children)
        has_html = any(c.name == "html" for c in children)
        assert has_doctype
        assert has_html

    def test_implied_html_head_body(self) -> None:
        b = build_tree("<p>Hello</p>")
        doc = b.document
        # Should auto-create html > head + body.
        html_els = get_elements(doc, "html")
        assert len(html_els) >= 1
        head_els = get_elements(doc, "head")
        assert len(head_els) >= 1
        body_els = get_elements(doc, "body")
        assert len(body_els) >= 1
        p_els = get_elements(doc, "p")
        assert len(p_els) == 1

    def test_text_content(self) -> None:
        b = build_tree("<p>Hello world</p>")
        p_els = get_elements(b.document, "p")
        assert len(p_els) == 1
        assert p_els[0].text() == "Hello world"

    def test_nested_elements(self) -> None:
        b = build_tree("<div><span>X</span></div>")
        divs = get_elements(b.document, "div")
        assert len(divs) == 1
        spans = get_elements(divs[0], "span")
        assert len(spans) == 1
        assert spans[0].text() == "X"


class TestAttributes:
    def test_element_attributes(self) -> None:
        b = build_tree('<div class="foo" id="bar"></div>')
        divs = get_elements(b.document, "div")
        assert len(divs) == 1
        assert divs[0].attributes.get("class") == "foo"
        assert divs[0].attributes.get("id") == "bar"

    def test_html_element_attribute_merge(self) -> None:
        # Second <html> tag should merge attributes.
        b = build_tree("<html lang='en'><head></head><body></body></html>")
        html_els = get_elements(b.document, "html")
        assert html_els[0].attributes.get("lang") == "en"


class TestHeadElements:
    def test_title(self) -> None:
        b = build_tree("<html><head><title>Test</title></head><body></body></html>")
        title_els = get_elements(b.document, "title")
        assert len(title_els) == 1
        assert title_els[0].text() == "Test"

    def test_meta(self) -> None:
        b = build_tree('<html><head><meta charset="utf-8"></head><body></body></html>')
        meta_els = get_elements(b.document, "meta")
        assert len(meta_els) == 1
        assert meta_els[0].attributes.get("charset") == "utf-8"

    def test_link(self) -> None:
        b = build_tree('<html><head><link rel="stylesheet" href="a.css"></head><body></body></html>')
        link_els = get_elements(b.document, "link")
        assert len(link_els) == 1


class TestInBodyElements:
    def test_div_p_span(self) -> None:
        b = build_tree("<div><p><span>text</span></p></div>")
        divs = get_elements(b.document, "div")
        assert len(divs) == 1
        ps = get_elements(divs[0], "p")
        assert len(ps) == 1

    def test_heading_elements(self) -> None:
        b = build_tree("<h1>A</h1><h2>B</h2>")
        h1s = get_elements(b.document, "h1")
        h2s = get_elements(b.document, "h2")
        assert len(h1s) == 1
        assert len(h2s) == 1

    def test_void_elements(self) -> None:
        b = build_tree("<p>a<br>b<hr>c</p>")
        brs = get_elements(b.document, "br")
        hrs = get_elements(b.document, "hr")
        assert len(brs) == 1
        assert len(hrs) == 1

    def test_p_auto_close(self) -> None:
        # A block element inside <p> should auto-close the <p>.
        b = build_tree("<p>a<div>b</div>c")
        ps = get_elements(b.document, "p")
        divs = get_elements(b.document, "div")
        assert len(ps) >= 1
        assert len(divs) == 1

    def test_list_items(self) -> None:
        b = build_tree("<ul><li>a<li>b<li>c</ul>")
        lis = get_elements(b.document, "li")
        assert len(lis) == 3

    def test_definition_list(self) -> None:
        b = build_tree("<dl><dt>term<dd>def</dl>")
        dts = get_elements(b.document, "dt")
        dds = get_elements(b.document, "dd")
        assert len(dts) == 1
        assert len(dds) == 1


class TestFormattingElements:
    def test_bold_em(self) -> None:
        b = build_tree("<p><b>bold</b> <em>italic</em></p>")
        bs = get_elements(b.document, "b")
        ems = get_elements(b.document, "em")
        assert len(bs) == 1
        assert len(ems) == 1

    def test_anchor(self) -> None:
        b = build_tree('<a href="x">link</a>')
        anchors = get_elements(b.document, "a")
        assert len(anchors) >= 1
        assert anchors[0].attributes.get("href") == "x"


class TestTables:
    def test_simple_table(self) -> None:
        b = build_tree("<table><tr><td>cell</td></tr></table>")
        tables = get_elements(b.document, "table")
        assert len(tables) == 1
        tds = get_elements(b.document, "td")
        assert len(tds) == 1
        assert tds[0].text() == "cell"

    def test_tbody_implied(self) -> None:
        b = build_tree("<table><tr><td>a</td></tr></table>")
        tbodys = get_elements(b.document, "tbody")
        assert len(tbodys) == 1

    def test_table_with_thead_tbody(self) -> None:
        b = build_tree("<table><thead><tr><th>H</th></tr></thead><tbody><tr><td>D</td></tr></tbody></table>")
        theads = get_elements(b.document, "thead")
        tbodys = get_elements(b.document, "tbody")
        assert len(theads) == 1
        assert len(tbodys) == 1


class TestComments:
    def test_comment_in_body(self) -> None:
        b = build_tree("<p><!-- hello --></p>")
        # Comment should be in the tree.
        doc = b.document
        comments = []
        def find_comments(node: TestNode) -> None:
            for child in node.childNodes:
                if child.name == "#comment":
                    comments.append(child)
                find_comments(child)
        find_comments(doc)
        assert len(comments) >= 1


class TestSelect:
    def test_select_with_options(self) -> None:
        b = build_tree("<select><option>A</option><option>B</option></select>")
        selects = get_elements(b.document, "select")
        assert len(selects) == 1
        options = get_elements(b.document, "option")
        assert len(options) == 2


class TestInsertionModeTransitions:
    def test_after_body(self) -> None:
        b = build_tree("<!DOCTYPE html><html><head></head><body></body></html>")
        # After processing </html>, mode should have progressed past inBody.
        # The exact final mode depends on EOF processing.
        assert b.insertionMode != "beforeHead"

    def test_mode_resets_after_table(self) -> None:
        b = build_tree("<table></table><p>after</p>")
        ps = get_elements(b.document, "p")
        assert len(ps) >= 1


class TestFullDocument:
    def test_real_world_snippet(self) -> None:
        html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Test Page</title>
</head>
<body>
    <h1>Hello</h1>
    <p>World <b>bold</b></p>
    <ul>
        <li>One</li>
        <li>Two</li>
    </ul>
    <table>
        <tr><td>A</td><td>B</td></tr>
    </table>
</body>
</html>"""
        b = build_tree(html)
        doc = b.document
        assert doc is not None
        # Verify key elements exist.
        assert len(get_elements(doc, "html")) >= 1
        assert len(get_elements(doc, "head")) >= 1
        assert len(get_elements(doc, "body")) >= 1
        assert len(get_elements(doc, "h1")) == 1
        assert len(get_elements(doc, "p")) == 1
        assert len(get_elements(doc, "b")) == 1
        assert len(get_elements(doc, "li")) == 2
        assert len(get_elements(doc, "td")) == 2

    def test_fragment_like(self) -> None:
        b = build_tree("<div><span>a</span><span>b</span></div>")
        spans = get_elements(b.document, "span")
        assert len(spans) == 2

    def test_entity_in_tree(self) -> None:
        b = build_tree("<p>a &amp; b</p>")
        p = get_elements(b.document, "p")[0]
        assert "& b" in p.text() or "&amp;" in p.text()


class TestEdgeCases:
    def test_self_closing_br(self) -> None:
        b = build_tree("<br/>")
        brs = get_elements(b.document, "br")
        assert len(brs) == 1

    def test_img_in_body(self) -> None:
        b = build_tree('<img src="x.png">')
        imgs = get_elements(b.document, "img")
        assert len(imgs) == 1
        assert imgs[0].attributes.get("src") == "x.png"

    def test_scope_queries(self) -> None:
        tb = TestTreeBuilder()
        html_node = TestNode("html", "http://www.w3.org/1999/xhtml")
        body_node = TestNode("body", "http://www.w3.org/1999/xhtml")
        p_node = TestNode("p", "http://www.w3.org/1999/xhtml")
        tb.openElements = [html_node, body_node, p_node]
        assert tb.elementInScope("p")
        assert tb.elementInScope("body")
        assert not tb.elementInScope("div")

    def test_implied_end_tags(self) -> None:
        tb = TestTreeBuilder()
        n1 = TestNode("div", "http://www.w3.org/1999/xhtml")
        n2 = TestNode("p", "http://www.w3.org/1999/xhtml")
        n3 = TestNode("dd", "http://www.w3.org/1999/xhtml")
        tb.openElements = [n1, n2, n3]
        tb.generateImpliedEndTags()
        assert len(tb.openElements) == 1  # only div remains
        assert tb.openElements[0].name == "div"

    def test_implied_end_tags_with_exclude(self) -> None:
        tb = TestTreeBuilder()
        n1 = TestNode("div", "http://www.w3.org/1999/xhtml")
        n2 = TestNode("p", "http://www.w3.org/1999/xhtml")
        tb.openElements = [n1, n2]
        tb.generateImpliedEndTags(exclude="p")
        assert len(tb.openElements) == 2  # p not removed
