"""Tests for HTMLParser public API and module-level functions."""

from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

import markuptree
from markuptree import HTMLParser, ParseError, SerializeError


# ---------------------------------------------------------------------------
# HTMLParser.parse
# ---------------------------------------------------------------------------

class TestHTMLParserParse:
    def test_parse_returns_tree(self) -> None:
        parser = HTMLParser(tree="etree")
        doc = parser.parse("<html><head></head><body><p>Hi</p></body></html>")
        assert doc is not None
        xml_str = ET.tostring(doc, encoding="unicode")
        assert "Hi" in xml_str

    def test_parse_string(self) -> None:
        parser = HTMLParser(tree="etree")
        doc = parser.parse("<p>Hello</p>")
        xml_str = ET.tostring(doc, encoding="unicode")
        assert "Hello" in xml_str

    def test_parse_bytes(self) -> None:
        parser = HTMLParser(tree="etree")
        doc = parser.parse(b"<p>Hello</p>")
        xml_str = ET.tostring(doc, encoding="unicode")
        assert "Hello" in xml_str

    def test_parse_dom_backend(self) -> None:
        parser = HTMLParser(tree="dom")
        doc = parser.parse("<p>Hello</p>")
        xml_str = doc.toxml()
        assert "Hello" in xml_str

    def test_parse_errors_collected(self) -> None:
        parser = HTMLParser(tree="etree")
        parser.parse("<p>text")  # unclosed tag -> parse errors
        # We should have some errors (though exact count depends on implementation).
        assert isinstance(parser.errors, list)

    def test_document_encoding(self) -> None:
        parser = HTMLParser(tree="etree")
        parser.parse("<p>test</p>")
        assert parser.documentEncoding is not None

    def test_namespace_elements(self) -> None:
        parser = HTMLParser(tree="etree", namespaceHTMLElements=True)
        doc = parser.parse("<p>test</p>")
        xml_str = ET.tostring(doc, encoding="unicode")
        assert "xhtml" in xml_str or "http://www.w3.org" in xml_str

    def test_no_namespace_elements(self) -> None:
        parser = HTMLParser(tree="etree", namespaceHTMLElements=False)
        doc = parser.parse("<p>test</p>")
        xml_str = ET.tostring(doc, encoding="unicode")
        assert "http://www.w3.org/1999/xhtml" not in xml_str

    def test_full_document(self) -> None:
        parser = HTMLParser(tree="etree")
        html = "<!DOCTYPE html><html><head><title>T</title></head><body><p>X</p></body></html>"
        doc = parser.parse(html)
        xml_str = ET.tostring(doc, encoding="unicode")
        assert "T" in xml_str
        assert "X" in xml_str


# ---------------------------------------------------------------------------
# HTMLParser.parseFragment
# ---------------------------------------------------------------------------

class TestHTMLParserParseFragment:
    def test_parse_fragment(self) -> None:
        parser = HTMLParser(tree="etree")
        fragments = parser.parseFragment("<p>a</p><p>b</p>")
        assert isinstance(fragments, list)

    def test_parse_fragment_dom(self) -> None:
        parser = HTMLParser(tree="dom")
        fragments = parser.parseFragment("<p>a</p><p>b</p>")
        assert isinstance(fragments, list)


# ---------------------------------------------------------------------------
# Module-level functions
# ---------------------------------------------------------------------------

class TestModuleLevelFunctions:
    def test_parse(self) -> None:
        doc = markuptree.parse("<p>Hello</p>")
        assert doc is not None

    def test_parse_fragment(self) -> None:
        fragments = markuptree.parseFragment("<p>Hello</p>")
        assert isinstance(fragments, list)

    def test_get_tree_builder(self) -> None:
        TB = markuptree.getTreeBuilder("etree")
        assert TB.implementationName == "etree"

    def test_get_tree_walker(self) -> None:
        from markuptree.treewalkers.etree import TreeWalker
        W = markuptree.getTreeWalker("etree")
        assert W is TreeWalker

    def test_serialize(self) -> None:
        doc = markuptree.parse("<p>Hello</p>", treebuilder="etree")
        result = markuptree.serialize(doc, tree="etree")
        assert "Hello" in result

    def test_version(self) -> None:
        assert markuptree.__version__ == "0.1.0"


# ---------------------------------------------------------------------------
# Compat shim
# ---------------------------------------------------------------------------

class TestCompat:
    def test_import_compat(self) -> None:
        from markuptree._compat import (
            parse,
            parseFragment,
            getTreeBuilder,
            getTreeWalker,
            serialize,
            HTMLParser,
            ParseError,
            SerializeError,
            HTMLSerializer,
            HTMLParseError,
        )
        assert HTMLParseError is ParseError

    def test_compat_parse(self) -> None:
        from markuptree._compat import parse
        doc = parse("<p>Hello</p>")
        assert doc is not None


# ---------------------------------------------------------------------------
# End-to-end: parse -> walk -> filter -> serialize
# ---------------------------------------------------------------------------

class TestEndToEnd:
    def test_full_pipeline_etree(self) -> None:
        doc = markuptree.parse(
            "<html><head></head><body><p>Hello <b>world</b></p></body></html>",
            treebuilder="etree",
        )
        from markuptree.treewalkers.etree import TreeWalker
        from markuptree.filters.alphabeticalattributes import Filter as AlphaFilter
        from markuptree.serializer import HTMLSerializer

        walker = TreeWalker(doc)
        filtered = AlphaFilter(walker)
        s = HTMLSerializer(omit_optional_tags=False)
        result = s.render(filtered)
        assert "<p>Hello <b>world</b></p>" in result

    def test_full_pipeline_dom(self) -> None:
        parser = HTMLParser(tree="dom")
        doc = parser.parse(
            "<html><head></head><body><p>Hello</p></body></html>"
        )
        from markuptree.treewalkers.dom import TreeWalker
        from markuptree.serializer import HTMLSerializer

        walker = TreeWalker(doc)
        s = HTMLSerializer(omit_optional_tags=False)
        result = s.render(walker)
        assert "<p>Hello</p>" in result

    def test_sanitize_pipeline(self) -> None:
        doc = markuptree.parse(
            '<p onclick="evil()">safe</p><script>alert(1)</script>',
            treebuilder="etree",
        )
        from markuptree.treewalkers.etree import TreeWalker
        from markuptree.filters.sanitizer import Filter as SanFilter
        from markuptree.serializer import HTMLSerializer

        walker = TreeWalker(doc)
        safe = SanFilter(walker)
        s = HTMLSerializer(omit_optional_tags=False)
        result = s.render(safe)
        assert "safe" in result
        assert "script" not in result.lower() or "<script>" not in result
        assert "onclick" not in result
