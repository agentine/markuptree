"""Tests for etree and dom TreeBuilder backends."""

from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from markuptree.inputstream import HTMLInputStream
from markuptree.tokenizer import HTMLTokenizer
from markuptree.treebuilders import getTreeBuilder


def parse_with(backend: str, html: str):
    """Parse HTML with the specified backend and return the tree builder."""
    TB = getTreeBuilder(backend)
    tb = TB()
    stream = HTMLInputStream(html)
    tok = HTMLTokenizer(stream)
    for token in tok:
        tb.processToken(token)
    return tb


# ---------------------------------------------------------------------------
# getTreeBuilder dispatch
# ---------------------------------------------------------------------------

class TestGetTreeBuilder:
    def test_etree(self) -> None:
        TB = getTreeBuilder("etree")
        assert TB.implementationName == "etree"

    def test_dom(self) -> None:
        TB = getTreeBuilder("dom")
        assert TB.implementationName == "dom"

    def test_case_insensitive(self) -> None:
        TB = getTreeBuilder("ETREE")
        assert TB.implementationName == "etree"

    def test_unknown(self) -> None:
        with pytest.raises(ValueError):
            getTreeBuilder("unknown_backend")


# ---------------------------------------------------------------------------
# etree backend
# ---------------------------------------------------------------------------

class TestEtreeBackend:
    def test_simple_doc(self) -> None:
        tb = parse_with("etree", "<html><head></head><body><p>Hi</p></body></html>")
        doc = tb.getDocument()
        assert isinstance(doc, ET.Element)
        xml_str = ET.tostring(doc, encoding="unicode")
        assert "Hi" in xml_str

    def test_attributes(self) -> None:
        tb = parse_with("etree", '<div class="foo" id="bar">text</div>')
        doc = tb.getDocument()
        xml_str = ET.tostring(doc, encoding="unicode")
        assert "foo" in xml_str
        assert "bar" in xml_str

    def test_nested_elements(self) -> None:
        tb = parse_with("etree", "<div><span><b>deep</b></span></div>")
        doc = tb.getDocument()
        xml_str = ET.tostring(doc, encoding="unicode")
        assert "deep" in xml_str

    def test_get_fragment(self) -> None:
        tb = parse_with("etree", "<p>a</p><p>b</p>")
        fragments = tb.getFragment()
        assert isinstance(fragments, list)

    def test_no_namespace(self) -> None:
        TB = getTreeBuilder("etree")
        tb = TB(namespaceHTMLElements=False)
        stream = HTMLInputStream("<p>test</p>")
        tok = HTMLTokenizer(stream)
        for token in tok:
            tb.processToken(token)
        doc = tb.getDocument()
        xml_str = ET.tostring(doc, encoding="unicode")
        # Without namespaces, tags should not have xmlns prefix.
        assert "http://www.w3.org/1999/xhtml" not in xml_str

    def test_comment(self) -> None:
        tb = parse_with("etree", "<p><!-- hello --></p>")
        doc = tb.getDocument()
        xml_str = ET.tostring(doc, encoding="unicode")
        assert "hello" in xml_str

    def test_doctype(self) -> None:
        tb = parse_with("etree", "<!DOCTYPE html><html><head></head><body></body></html>")
        doc = tb.getDocument()
        assert doc is not None

    def test_text_content(self) -> None:
        tb = parse_with("etree", "<p>Hello world</p>")
        doc = tb.getDocument()
        xml_str = ET.tostring(doc, encoding="unicode")
        assert "Hello world" in xml_str

    def test_mixed_content(self) -> None:
        tb = parse_with("etree", "<p>a<b>b</b>c</p>")
        doc = tb.getDocument()
        xml_str = ET.tostring(doc, encoding="unicode")
        assert "a" in xml_str
        assert "b" in xml_str
        assert "c" in xml_str


# ---------------------------------------------------------------------------
# dom backend
# ---------------------------------------------------------------------------

class TestDomBackend:
    def test_simple_doc(self) -> None:
        tb = parse_with("dom", "<html><head></head><body><p>Hi</p></body></html>")
        doc = tb.getDocument()
        xml_str = doc.toxml()
        assert "Hi" in xml_str

    def test_attributes(self) -> None:
        tb = parse_with("dom", '<div class="foo" id="bar">text</div>')
        doc = tb.getDocument()
        xml_str = doc.toxml()
        assert "foo" in xml_str
        assert "bar" in xml_str

    def test_nested_elements(self) -> None:
        tb = parse_with("dom", "<div><span><b>deep</b></span></div>")
        doc = tb.getDocument()
        xml_str = doc.toxml()
        assert "deep" in xml_str

    def test_get_fragment(self) -> None:
        tb = parse_with("dom", "<p>a</p><p>b</p>")
        fragments = tb.getFragment()
        assert isinstance(fragments, list)

    def test_comment(self) -> None:
        tb = parse_with("dom", "<p><!-- hello --></p>")
        doc = tb.getDocument()
        xml_str = doc.toxml()
        assert "hello" in xml_str

    def test_doctype(self) -> None:
        tb = parse_with("dom", "<!DOCTYPE html><html><head></head><body></body></html>")
        doc = tb.getDocument()
        xml_str = doc.toxml()
        assert "html" in xml_str

    def test_text_content(self) -> None:
        tb = parse_with("dom", "<p>Hello world</p>")
        doc = tb.getDocument()
        xml_str = doc.toxml()
        assert "Hello world" in xml_str

    def test_mixed_content(self) -> None:
        tb = parse_with("dom", "<p>a<b>b</b>c</p>")
        doc = tb.getDocument()
        xml_str = doc.toxml()
        assert "a" in xml_str
        assert "b" in xml_str

    def test_table(self) -> None:
        tb = parse_with("dom", "<table><tr><td>cell</td></tr></table>")
        doc = tb.getDocument()
        xml_str = doc.toxml()
        assert "cell" in xml_str
        assert "table" in xml_str


# ---------------------------------------------------------------------------
# Cross-backend consistency
# ---------------------------------------------------------------------------

class TestCrossBackend:
    def test_both_parse_same_text(self) -> None:
        html = "<p>Hello <b>world</b></p>"
        etree_tb = parse_with("etree", html)
        dom_tb = parse_with("dom", html)

        etree_xml = ET.tostring(etree_tb.getDocument(), encoding="unicode")
        dom_xml = dom_tb.getDocument().toxml()

        # Both should contain the same text.
        assert "Hello" in etree_xml
        assert "Hello" in dom_xml
        assert "world" in etree_xml
        assert "world" in dom_xml

    def test_both_handle_full_doc(self) -> None:
        html = "<!DOCTYPE html><html><head><title>T</title></head><body><p>X</p></body></html>"
        for backend in ("etree", "dom"):
            tb = parse_with(backend, html)
            doc = tb.getDocument()
            assert doc is not None
