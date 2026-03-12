"""Tests for tree walkers, serializer, and filters."""

from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from markuptree.inputstream import HTMLInputStream
from markuptree.tokenizer import HTMLTokenizer
from markuptree.treebuilders import getTreeBuilder
from markuptree.treewalkers import getTreeWalker
from markuptree.treewalkers.base import TreeWalker as BaseTreeWalker
from markuptree.treewalkers.etree import TreeWalker as EtreeWalker
from markuptree.treewalkers.dom import TreeWalker as DomWalker
from markuptree.serializer import HTMLSerializer
from markuptree.filters.base import Filter as BaseFilter
from markuptree.filters.alphabeticalattributes import Filter as AlphaFilter
from markuptree.filters.inject_meta_charset import Filter as MetaFilter
from markuptree.filters.whitespace import Filter as WSFilter
from markuptree.filters.optionaltags import Filter as OptTagsFilter
from markuptree.filters.sanitizer import Filter as SanFilter
from markuptree.filters.lint import Filter as LintFilter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_etree(html: str):
    """Parse HTML with etree backend and return the root ET.Element."""
    TB = getTreeBuilder("etree")
    tb = TB()
    stream = HTMLInputStream(html)
    tok = HTMLTokenizer(stream)
    for token in tok:
        tb.processToken(token)
    return tb.getDocument()


def _parse_dom(html: str):
    """Parse HTML with dom backend and return the minidom Document."""
    TB = getTreeBuilder("dom")
    tb = TB()
    stream = HTMLInputStream(html)
    tok = HTMLTokenizer(stream)
    for token in tok:
        tb.processToken(token)
    return tb.getDocument()


def _serialize(walker, **kwargs):
    s = HTMLSerializer(omit_optional_tags=False, **kwargs)
    return s.render(walker)


# ---------------------------------------------------------------------------
# getTreeWalker dispatch
# ---------------------------------------------------------------------------

class TestGetTreeWalker:
    def test_etree(self) -> None:
        W = getTreeWalker("etree")
        assert W is EtreeWalker

    def test_dom(self) -> None:
        W = getTreeWalker("dom")
        assert W is DomWalker

    def test_unknown(self) -> None:
        with pytest.raises(ValueError):
            getTreeWalker("nonexistent")


# ---------------------------------------------------------------------------
# Etree TreeWalker
# ---------------------------------------------------------------------------

class TestEtreeWalker:
    def test_simple(self) -> None:
        doc = _parse_etree("<p>Hello</p>")
        tokens = list(EtreeWalker(doc))
        types = [t["type"] for t in tokens]
        assert "StartTag" in types
        assert "Characters" in types
        assert "EndTag" in types

    def test_text_content(self) -> None:
        doc = _parse_etree("<p>Hello world</p>")
        result = _serialize(EtreeWalker(doc))
        assert "Hello world" in result

    def test_nested(self) -> None:
        doc = _parse_etree("<div><span><b>deep</b></span></div>")
        result = _serialize(EtreeWalker(doc))
        assert "<b>deep</b>" in result
        assert "<span>" in result

    def test_attributes(self) -> None:
        doc = _parse_etree('<p class="foo" id="bar">x</p>')
        result = _serialize(EtreeWalker(doc), quote_attr_values="always")
        assert 'class="foo"' in result
        assert 'id="bar"' in result

    def test_void_elements(self) -> None:
        doc = _parse_etree("<p>a<br>b</p>")
        tokens = list(EtreeWalker(doc))
        br_tokens = [t for t in tokens if t.get("name") == "br"]
        assert len(br_tokens) == 1
        assert br_tokens[0]["type"] == "EmptyTag"

    def test_comment(self) -> None:
        doc = _parse_etree("<p><!-- hello --></p>")
        result = _serialize(EtreeWalker(doc))
        assert "<!--" in result
        assert "hello" in result

    def test_full_document(self) -> None:
        html = "<html><head><title>T</title></head><body><p>X</p></body></html>"
        doc = _parse_etree(html)
        result = _serialize(EtreeWalker(doc))
        assert "<title>T</title>" in result
        assert "<p>X</p>" in result

    def test_whitespace_tokens(self) -> None:
        doc = _parse_etree("<p>   </p>")
        tokens = list(EtreeWalker(doc))
        space_tokens = [t for t in tokens if t["type"] == "SpaceCharacters"]
        assert len(space_tokens) > 0


# ---------------------------------------------------------------------------
# Dom TreeWalker
# ---------------------------------------------------------------------------

class TestDomWalker:
    def test_simple(self) -> None:
        doc = _parse_dom("<p>Hello</p>")
        tokens = list(DomWalker(doc))
        types = [t["type"] for t in tokens]
        assert "StartTag" in types
        assert "Characters" in types
        assert "EndTag" in types

    def test_text_content(self) -> None:
        doc = _parse_dom("<p>Hello world</p>")
        result = _serialize(DomWalker(doc))
        assert "Hello world" in result

    def test_nested(self) -> None:
        doc = _parse_dom("<div><span><b>deep</b></span></div>")
        result = _serialize(DomWalker(doc))
        assert "<b>deep</b>" in result

    def test_attributes(self) -> None:
        doc = _parse_dom('<p class="foo" id="bar">x</p>')
        result = _serialize(DomWalker(doc), quote_attr_values="always")
        assert 'class="foo"' in result
        assert 'id="bar"' in result

    def test_comment(self) -> None:
        doc = _parse_dom("<p><!-- hello --></p>")
        result = _serialize(DomWalker(doc))
        assert "<!-- hello -->" in result

    def test_doctype(self) -> None:
        doc = _parse_dom("<!DOCTYPE html><html><head></head><body></body></html>")
        tokens = list(DomWalker(doc))
        doctypes = [t for t in tokens if t["type"] == "Doctype"]
        assert len(doctypes) == 1
        assert doctypes[0]["name"] == "html"

    def test_full_document(self) -> None:
        html = "<html><head><title>T</title></head><body><p>X</p></body></html>"
        doc = _parse_dom(html)
        result = _serialize(DomWalker(doc))
        assert "<title>T</title>" in result
        assert "<p>X</p>" in result


# ---------------------------------------------------------------------------
# Cross-walker consistency
# ---------------------------------------------------------------------------

class TestCrossWalker:
    def test_same_output(self) -> None:
        html = "<html><head></head><body><p>Hello <b>world</b></p></body></html>"
        etree_doc = _parse_etree(html)
        dom_doc = _parse_dom(html)

        etree_result = _serialize(EtreeWalker(etree_doc))
        dom_result = _serialize(DomWalker(dom_doc))

        # Both should contain the essential content.
        for s in ("Hello", "world", "<p>", "</p>", "<b>", "</b>"):
            assert s in etree_result, f"{s!r} not in etree result"
            assert s in dom_result, f"{s!r} not in dom result"


# ---------------------------------------------------------------------------
# HTMLSerializer
# ---------------------------------------------------------------------------

class TestHTMLSerializer:
    def test_basic_render(self) -> None:
        doc = _parse_etree("<p>Hello</p>")
        result = _serialize(EtreeWalker(doc))
        assert "<p>Hello</p>" in result

    def test_quote_attr_always(self) -> None:
        doc = _parse_etree('<div class="foo">x</div>')
        result = _serialize(EtreeWalker(doc), quote_attr_values="always")
        assert 'class="foo"' in result

    def test_quote_attr_legacy(self) -> None:
        doc = _parse_etree('<div class="simple">x</div>')
        result = _serialize(EtreeWalker(doc), quote_attr_values="legacy")
        # "simple" has no special chars, so quotes can be omitted.
        assert "class=simple" in result

    def test_boolean_attribute(self) -> None:
        doc = _parse_etree('<input disabled="disabled">')
        tokens = list(EtreeWalker(doc))
        # Find the input token.
        input_tokens = [t for t in tokens if t.get("name") == "input"]
        assert len(input_tokens) > 0
        result = _serialize(EtreeWalker(doc), minimize_boolean_attributes=True)
        # Should have "disabled" without ="disabled".
        assert " disabled>" in result or " disabled " in result or " disabled/>" in result

    def test_trailing_solidus(self) -> None:
        doc = _parse_etree("<br>")
        result = _serialize(EtreeWalker(doc), use_trailing_solidus=True)
        assert "<br />" in result

    def test_no_trailing_solidus(self) -> None:
        doc = _parse_etree("<br>")
        result = _serialize(EtreeWalker(doc), use_trailing_solidus=False)
        assert "<br>" in result

    def test_doctype(self) -> None:
        doc = _parse_dom("<!DOCTYPE html><html><head></head><body></body></html>")
        result = _serialize(DomWalker(doc))
        assert "<!DOCTYPE html>" in result

    def test_comment(self) -> None:
        doc = _parse_etree("<p><!-- test --></p>")
        result = _serialize(EtreeWalker(doc))
        assert "<!-- test -->" in result

    def test_escape_text(self) -> None:
        doc = _parse_etree("<p>&amp; &lt; &gt;</p>")
        result = _serialize(EtreeWalker(doc))
        assert "&amp;" in result
        assert "&lt;" in result
        assert "&gt;" in result

    def test_unknown_option_raises(self) -> None:
        with pytest.raises(TypeError):
            HTMLSerializer(nonexistent_option=True)

    def test_serialize_function(self) -> None:
        doc = _parse_etree("<p>Hi</p>")
        from markuptree.serializer import serialize as ser_func
        result = ser_func(doc, tree="etree", omit_optional_tags=False)
        assert "<p>Hi</p>" in result


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------

class TestAlphabeticalAttributesFilter:
    def test_sorts_attrs(self) -> None:
        doc = _parse_etree('<div z="1" a="2" m="3">x</div>')
        walker = EtreeWalker(doc)
        filtered = AlphaFilter(walker)
        result = _serialize(filtered, quote_attr_values="always")
        # Attributes should be sorted: a, m, z.
        a_pos = result.find('a="2"')
        m_pos = result.find('m="3"')
        z_pos = result.find('z="1"')
        assert a_pos < m_pos < z_pos

    def test_passthrough_non_tags(self) -> None:
        doc = _parse_etree("<p>text</p>")
        walker = EtreeWalker(doc)
        filtered = AlphaFilter(walker)
        result = _serialize(filtered)
        assert "text" in result


class TestInjectMetaCharsetFilter:
    def test_injects_charset(self) -> None:
        doc = _parse_etree("<html><head></head><body>x</body></html>")
        walker = EtreeWalker(doc)
        filtered = MetaFilter(walker, encoding="utf-8")
        result = _serialize(filtered)
        assert 'charset' in result.lower()

    def test_replaces_existing_charset(self) -> None:
        doc = _parse_etree('<html><head><meta charset="ascii"></head><body>x</body></html>')
        walker = EtreeWalker(doc)
        filtered = MetaFilter(walker, encoding="utf-8")
        tokens = list(filtered)
        meta_tokens = [t for t in tokens if t.get("name") == "meta"]
        assert any(t.get("data", {}).get("charset") == "utf-8" for t in meta_tokens)


class TestWhitespaceFilter:
    def test_collapses_spaces(self) -> None:
        # Create tokens manually since parser might normalize whitespace.
        tokens = [
            {"type": "SpaceCharacters", "data": "   \t\n  "},
            {"type": "Characters", "data": "hello   world"},
        ]
        filtered = list(WSFilter(tokens))
        space_tok = [t for t in filtered if t["type"] == "SpaceCharacters"]
        assert space_tok[0]["data"] == " "
        char_tok = [t for t in filtered if t["type"] == "Characters"]
        assert char_tok[0]["data"] == "hello world"

    def test_preserves_pre_whitespace(self) -> None:
        tokens = [
            {"type": "StartTag", "name": "pre", "data": {}},
            {"type": "SpaceCharacters", "data": "   \n  "},
            {"type": "EndTag", "name": "pre"},
        ]
        filtered = list(WSFilter(tokens))
        space_tok = [t for t in filtered if t["type"] == "SpaceCharacters"]
        assert space_tok[0]["data"] == "   \n  "


class TestOptionalTagsFilter:
    def test_omits_li_end(self) -> None:
        tokens = [
            {"type": "StartTag", "namespace": None, "name": "ul", "data": {}},
            {"type": "StartTag", "namespace": None, "name": "li", "data": {}},
            {"type": "Characters", "data": "a"},
            {"type": "EndTag", "namespace": None, "name": "li"},
            {"type": "StartTag", "namespace": None, "name": "li", "data": {}},
            {"type": "Characters", "data": "b"},
            {"type": "EndTag", "namespace": None, "name": "li"},
            {"type": "EndTag", "namespace": None, "name": "ul"},
        ]
        filtered = list(OptTagsFilter(tokens))
        # The first </li> before the second <li> should be omitted.
        end_lis = [t for t in filtered if t["type"] == "EndTag" and t["name"] == "li"]
        assert len(end_lis) < 2

    def test_omits_p_end_before_div(self) -> None:
        tokens = [
            {"type": "StartTag", "namespace": None, "name": "p", "data": {}},
            {"type": "Characters", "data": "text"},
            {"type": "EndTag", "namespace": None, "name": "p"},
            {"type": "StartTag", "namespace": None, "name": "div", "data": {}},
            {"type": "Characters", "data": "block"},
            {"type": "EndTag", "namespace": None, "name": "div"},
        ]
        filtered = list(OptTagsFilter(tokens))
        end_ps = [t for t in filtered if t["type"] == "EndTag" and t["name"] == "p"]
        assert len(end_ps) == 0


class TestSanitizerFilter:
    def test_strips_script(self) -> None:
        tokens = [
            {"type": "StartTag", "name": "p", "data": {}},
            {"type": "Characters", "data": "safe"},
            {"type": "EndTag", "name": "p"},
            {"type": "StartTag", "name": "script", "data": {}},
            {"type": "Characters", "data": "alert(1)"},
            {"type": "EndTag", "name": "script"},
        ]
        filtered = list(SanFilter(tokens))
        names = [t.get("name") for t in filtered]
        assert "script" not in names

    def test_strips_unsafe_attrs(self) -> None:
        tokens = [
            {"type": "StartTag", "name": "a", "data": {"href": "http://ok.com", "onclick": "evil()"}},
            {"type": "Characters", "data": "link"},
            {"type": "EndTag", "name": "a"},
        ]
        filtered = list(SanFilter(tokens))
        a_tokens = [t for t in filtered if t.get("name") == "a" and t["type"] == "StartTag"]
        assert "onclick" not in a_tokens[0]["data"]
        assert "href" in a_tokens[0]["data"]

    def test_strips_javascript_uri(self) -> None:
        tokens = [
            {"type": "StartTag", "name": "a", "data": {"href": "javascript:alert(1)"}},
            {"type": "Characters", "data": "link"},
            {"type": "EndTag", "name": "a"},
        ]
        filtered = list(SanFilter(tokens))
        a_tokens = [t for t in filtered if t.get("name") == "a" and t["type"] == "StartTag"]
        assert "href" not in a_tokens[0]["data"]

    def test_allows_safe_elements(self) -> None:
        tokens = [
            {"type": "StartTag", "name": "b", "data": {}},
            {"type": "Characters", "data": "bold"},
            {"type": "EndTag", "name": "b"},
        ]
        filtered = list(SanFilter(tokens))
        assert len(filtered) == 3


class TestLintFilter:
    def test_warns_void_starttag(self) -> None:
        tokens = [
            {"type": "StartTag", "name": "br", "data": {}},
        ]
        filtered = list(LintFilter(tokens))
        errors = [t for t in filtered if t["type"] == "SerializeError"]
        assert len(errors) == 1
        assert "Void element" in errors[0]["data"]

    def test_warns_void_endtag(self) -> None:
        tokens = [
            {"type": "EmptyTag", "name": "br", "data": {}},
            {"type": "EndTag", "name": "br"},
        ]
        filtered = list(LintFilter(tokens))
        errors = [t for t in filtered if t["type"] == "SerializeError"]
        assert len(errors) == 1
        assert "end tag" in errors[0]["data"]

    def test_no_error_for_valid(self) -> None:
        tokens = [
            {"type": "StartTag", "name": "p", "data": {}},
            {"type": "Characters", "data": "text"},
            {"type": "EndTag", "name": "p"},
        ]
        filtered = list(LintFilter(tokens))
        errors = [t for t in filtered if t["type"] == "SerializeError"]
        assert len(errors) == 0


# ---------------------------------------------------------------------------
# Base filter passthrough
# ---------------------------------------------------------------------------

class TestBaseFilter:
    def test_passthrough(self) -> None:
        tokens = [
            {"type": "Characters", "data": "hello"},
            {"type": "StartTag", "name": "p", "data": {}},
        ]
        filtered = list(BaseFilter(tokens))
        assert filtered == tokens
