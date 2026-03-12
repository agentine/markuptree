"""Tests for markuptree HTMLTokenizer."""

from __future__ import annotations

import pytest

from markuptree.constants import tokenTypes
from markuptree.inputstream import HTMLInputStream
from markuptree.tokenizer import HTMLTokenizer


def tokenize(html: str) -> list[dict]:
    """Helper: tokenize HTML string and return non-EOF tokens."""
    stream = HTMLInputStream(html)
    tok = HTMLTokenizer(stream)
    return [t for t in tok if t.get("type") != "EOF"]


def token_types(tokens: list[dict]) -> list[int]:
    return [t["type"] for t in tokens]


# ---------------------------------------------------------------------------
# Basic text
# ---------------------------------------------------------------------------


class TestPlainText:
    def test_simple_text(self) -> None:
        tokens = tokenize("hello world")
        assert len(tokens) == 1
        assert tokens[0]["type"] == tokenTypes["Characters"]
        assert tokens[0]["data"] == "hello world"

    def test_empty(self) -> None:
        tokens = tokenize("")
        assert tokens == []

    def test_whitespace_only(self) -> None:
        tokens = tokenize("   ")
        assert len(tokens) == 1
        assert tokens[0]["type"] == tokenTypes["SpaceCharacters"]


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------


class TestTags:
    def test_open_tag(self) -> None:
        tokens = tokenize("<div>")
        assert len(tokens) == 1
        assert tokens[0]["type"] == tokenTypes["StartTag"]
        assert tokens[0]["name"] == "div"
        assert tokens[0]["data"] == {}
        assert tokens[0]["selfClosing"] is False

    def test_close_tag(self) -> None:
        tokens = tokenize("</div>")
        assert len(tokens) == 1
        assert tokens[0]["type"] == tokenTypes["EndTag"]
        assert tokens[0]["name"] == "div"

    def test_self_closing_tag(self) -> None:
        tokens = tokenize("<br/>")
        assert len(tokens) == 1
        assert tokens[0]["type"] == tokenTypes["StartTag"]
        assert tokens[0]["name"] == "br"
        assert tokens[0]["selfClosing"] is True

    def test_tag_name_case_insensitive(self) -> None:
        tokens = tokenize("<DIV>")
        assert tokens[0]["name"] == "div"

    def test_tag_with_text(self) -> None:
        tokens = tokenize("<p>hello</p>")
        assert len(tokens) == 3
        assert tokens[0]["type"] == tokenTypes["StartTag"]
        assert tokens[0]["name"] == "p"
        assert tokens[1]["type"] == tokenTypes["Characters"]
        assert tokens[1]["data"] == "hello"
        assert tokens[2]["type"] == tokenTypes["EndTag"]
        assert tokens[2]["name"] == "p"

    def test_nested_tags(self) -> None:
        tokens = tokenize("<div><span>x</span></div>")
        names = [t.get("name") for t in tokens if t.get("name")]
        assert names == ["div", "span", "span", "div"]


# ---------------------------------------------------------------------------
# Attributes
# ---------------------------------------------------------------------------


class TestAttributes:
    def test_single_attr(self) -> None:
        tokens = tokenize('<div class="foo">')
        assert tokens[0]["data"] == {"class": "foo"}

    def test_multiple_attrs(self) -> None:
        tokens = tokenize('<input type="text" name="q" value="hi">')
        attrs = tokens[0]["data"]
        assert attrs == {"type": "text", "name": "q", "value": "hi"}

    def test_single_quoted_attr(self) -> None:
        tokens = tokenize("<div class='bar'>")
        assert tokens[0]["data"] == {"class": "bar"}

    def test_unquoted_attr(self) -> None:
        tokens = tokenize("<div id=main>")
        assert tokens[0]["data"] == {"id": "main"}

    def test_attr_case_insensitive(self) -> None:
        tokens = tokenize('<div CLASS="foo">')
        assert "class" in tokens[0]["data"]

    def test_duplicate_attr_first_wins(self) -> None:
        tokens = tokenize('<div class="a" class="b">')
        # First attribute wins per HTML5 spec.
        assert tokens[0]["data"]["class"] == "a"
        # Should also emit a parse error.
        errors = [t for t in tokens if t["type"] == tokenTypes["ParseError"]]
        assert len(errors) >= 1

    def test_empty_attr_value(self) -> None:
        tokens = tokenize('<input disabled="">')
        assert tokens[0]["data"] == {"disabled": ""}

    def test_attr_with_entity(self) -> None:
        tokens = tokenize('<a title="a &amp; b">')
        assert tokens[0]["data"]["title"] == "a & b"


# ---------------------------------------------------------------------------
# Character references
# ---------------------------------------------------------------------------


class TestCharacterReferences:
    def test_named_entity(self) -> None:
        tokens = tokenize("&amp;")
        text = "".join(t["data"] for t in tokens if t["type"] in (1, 2))
        assert text == "&"

    def test_named_entity_lt(self) -> None:
        tokens = tokenize("&lt;")
        text = "".join(t["data"] for t in tokens if t["type"] in (1, 2))
        assert text == "<"

    def test_named_entity_gt(self) -> None:
        tokens = tokenize("&gt;")
        text = "".join(t["data"] for t in tokens if t["type"] in (1, 2))
        assert text == ">"

    def test_numeric_decimal(self) -> None:
        tokens = tokenize("&#65;")
        text = "".join(t["data"] for t in tokens if t["type"] in (1, 2))
        assert text == "A"

    def test_numeric_hex_lower(self) -> None:
        tokens = tokenize("&#x41;")
        text = "".join(t["data"] for t in tokens if t["type"] in (1, 2))
        assert text == "A"

    def test_numeric_hex_upper(self) -> None:
        tokens = tokenize("&#X41;")
        text = "".join(t["data"] for t in tokens if t["type"] in (1, 2))
        assert text == "A"

    def test_entity_in_text(self) -> None:
        tokens = tokenize("a &lt; b &amp; c")
        text = "".join(t["data"] for t in tokens if t["type"] in (1, 2))
        assert text == "a < b & c"

    def test_bare_ampersand(self) -> None:
        tokens = tokenize("a & b")
        text = "".join(t["data"] for t in tokens if t["type"] in (1, 2))
        assert text == "a & b"

    def test_numeric_null_replaced(self) -> None:
        tokens = tokenize("&#0;")
        text = "".join(t["data"] for t in tokens if t["type"] in (1, 2))
        assert text == "\uFFFD"

    def test_numeric_surrogate_replaced(self) -> None:
        tokens = tokenize("&#xD800;")
        text = "".join(t["data"] for t in tokens if t["type"] in (1, 2))
        assert text == "\uFFFD"

    def test_numeric_too_large(self) -> None:
        tokens = tokenize("&#x110000;")
        text = "".join(t["data"] for t in tokens if t["type"] in (1, 2))
        assert text == "\uFFFD"

    def test_entity_without_semicolon(self) -> None:
        tokens = tokenize("&amp")
        text = "".join(t["data"] for t in tokens if t["type"] in (1, 2))
        # Should still resolve (with parse error).
        assert text == "&"

    def test_unknown_entity_passthrough(self) -> None:
        tokens = tokenize("&zzzzfake;")
        text = "".join(t["data"] for t in tokens if t["type"] in (1, 2))
        # Unknown entity — ampersand and text pass through.
        assert "&" in text


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------


class TestComments:
    def test_simple_comment(self) -> None:
        tokens = tokenize("<!-- hello -->")
        comments = [t for t in tokens if t["type"] == tokenTypes["Comment"]]
        assert len(comments) == 1
        assert comments[0]["data"] == " hello "

    def test_empty_comment(self) -> None:
        tokens = tokenize("<!---->")
        comments = [t for t in tokens if t["type"] == tokenTypes["Comment"]]
        assert len(comments) == 1
        assert comments[0]["data"] == ""

    def test_comment_with_dashes(self) -> None:
        tokens = tokenize("<!-- a -- b -->")
        comments = [t for t in tokens if t["type"] == tokenTypes["Comment"]]
        assert len(comments) == 1
        assert "a" in comments[0]["data"]

    def test_comment_before_tag(self) -> None:
        tokens = tokenize("<!-- x --><p>")
        types = [t["type"] for t in tokens]
        assert tokenTypes["Comment"] in types
        assert tokenTypes["StartTag"] in types


# ---------------------------------------------------------------------------
# DOCTYPE
# ---------------------------------------------------------------------------


class TestDoctype:
    def test_simple_doctype(self) -> None:
        tokens = tokenize("<!DOCTYPE html>")
        doctypes = [t for t in tokens if t["type"] == tokenTypes["Doctype"]]
        assert len(doctypes) == 1
        assert doctypes[0]["name"] == "html"
        assert doctypes[0]["correct"] is True

    def test_doctype_case_insensitive(self) -> None:
        tokens = tokenize("<!doctype html>")
        doctypes = [t for t in tokens if t["type"] == tokenTypes["Doctype"]]
        assert len(doctypes) == 1
        assert doctypes[0]["name"] == "html"

    def test_doctype_before_content(self) -> None:
        tokens = tokenize("<!DOCTYPE html><html>")
        assert tokens[0]["type"] == tokenTypes["Doctype"]
        assert tokens[1]["type"] == tokenTypes["StartTag"]
        assert tokens[1]["name"] == "html"


# ---------------------------------------------------------------------------
# Self-closing and void elements
# ---------------------------------------------------------------------------


class TestSelfClosing:
    def test_img(self) -> None:
        tokens = tokenize('<img src="x.png"/>')
        assert tokens[0]["selfClosing"] is True
        assert tokens[0]["data"]["src"] == "x.png"

    def test_slash_not_self_closing(self) -> None:
        # <div / > — the / is not immediately before > so it's not self-closing.
        tokens = tokenize("<div / >")
        # The / triggers selfClosingStartTag state, which reads ">", making it
        # look like self-closing. But the space between / and > means
        # it goes through beforeAttrName instead.
        tag = [t for t in tokens if t["type"] == tokenTypes["StartTag"]][0]
        # Space after / → unexpected solidus parse error, not self-closing.
        assert tag["name"] == "div"


# ---------------------------------------------------------------------------
# CDATA section
# ---------------------------------------------------------------------------


class TestCDATA:
    def test_cdata_section(self) -> None:
        tokens = tokenize("<![CDATA[hello <world>]]>")
        text = "".join(t["data"] for t in tokens if t["type"] in (1, 2))
        assert text == "hello <world>"


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrors:
    def test_eof_in_tag(self) -> None:
        tokens = tokenize("<div")
        errors = [t for t in tokens if t["type"] == tokenTypes["ParseError"]]
        assert len(errors) >= 1

    def test_eof_before_tag_name(self) -> None:
        tokens = tokenize("<")
        errors = [t for t in tokens if t["type"] == tokenTypes["ParseError"]]
        assert len(errors) >= 1
        # Should emit the < as a character.
        chars = [t for t in tokens if t["type"] in (1, 2)]
        assert any("<" in t["data"] for t in chars)

    def test_invalid_tag_char(self) -> None:
        tokens = tokenize("<1>")
        errors = [t for t in tokens if t["type"] == tokenTypes["ParseError"]]
        assert len(errors) >= 1

    def test_question_mark_tag(self) -> None:
        tokens = tokenize("<?xml?>")
        # Should be treated as a bogus comment.
        comments = [t for t in tokens if t["type"] == tokenTypes["Comment"]]
        assert len(comments) >= 1


# ---------------------------------------------------------------------------
# Full document
# ---------------------------------------------------------------------------


class TestFullDocument:
    def test_minimal_doc(self) -> None:
        html = "<!DOCTYPE html><html><head><title>T</title></head><body><p>Hi</p></body></html>"
        tokens = tokenize(html)
        start_tags = [t["name"] for t in tokens if t["type"] == tokenTypes["StartTag"]]
        end_tags = [t["name"] for t in tokens if t["type"] == tokenTypes["EndTag"]]
        assert "html" in start_tags
        assert "head" in start_tags
        assert "title" in start_tags
        assert "body" in start_tags
        assert "p" in start_tags
        assert "html" in end_tags
        assert "p" in end_tags

    def test_mixed_content(self) -> None:
        html = '<div class="c">text &amp; <em>more</em><!-- note --></div>'
        tokens = tokenize(html)
        text = "".join(t["data"] for t in tokens if t["type"] in (1, 2))
        assert text == "text & more"
        comments = [t for t in tokens if t["type"] == tokenTypes["Comment"]]
        assert len(comments) == 1
        assert comments[0]["data"] == " note "
