"""Tests for markuptree HTMLInputStream."""

from __future__ import annotations

import io

import pytest

from markuptree.inputstream import HTMLInputStream, EOF


class TestBasicReading:
    def test_read_string(self) -> None:
        s = HTMLInputStream("hello")
        assert s.char() == "h"
        assert s.char() == "e"
        assert s.char() == "l"
        assert s.char() == "l"
        assert s.char() == "o"
        assert s.char() is EOF

    def test_read_bytes(self) -> None:
        s = HTMLInputStream(b"hello")
        assert s.char() == "h"
        assert s.char() == "e"

    def test_read_filelike(self) -> None:
        s = HTMLInputStream(io.BytesIO(b"hello"))
        assert s.char() == "h"

    def test_empty(self) -> None:
        s = HTMLInputStream("")
        assert s.char() is EOF

    def test_eof_repeated(self) -> None:
        s = HTMLInputStream("a")
        assert s.char() == "a"
        assert s.char() is EOF
        assert s.char() is EOF


class TestNormalization:
    def test_null_replacement(self) -> None:
        s = HTMLInputStream("a\x00b")
        assert s.char() == "a"
        assert s.char() == "\uFFFD"
        assert s.char() == "b"

    def test_cr_lf_normalization(self) -> None:
        s = HTMLInputStream("a\r\nb")
        assert s.char() == "a"
        assert s.char() == "\n"
        assert s.char() == "b"

    def test_cr_normalization(self) -> None:
        s = HTMLInputStream("a\rb")
        assert s.char() == "a"
        assert s.char() == "\n"
        assert s.char() == "b"


class TestPosition:
    def test_line_column(self) -> None:
        s = HTMLInputStream("ab\ncd")
        s.char()  # a → (1, 1)
        assert s.position == (1, 1)
        s.char()  # b → (1, 2)
        assert s.position == (1, 2)
        s.char()  # \n → (2, 0)
        assert s.position == (2, 0)
        s.char()  # c → (2, 1)
        assert s.position == (2, 1)
        s.char()  # d → (2, 2)
        assert s.position == (2, 2)


class TestUnget:
    def test_unget_basic(self) -> None:
        s = HTMLInputStream("abc")
        c = s.char()
        assert c == "a"
        s.unget(c)
        assert s.char() == "a"
        assert s.char() == "b"

    def test_unget_eof(self) -> None:
        s = HTMLInputStream("a")
        s.char()
        s.unget(EOF)  # should not crash
        assert s.char() is EOF

    def test_unget_none(self) -> None:
        s = HTMLInputStream("a")
        s.unget(None)  # should not crash


class TestCharsUntil:
    def test_chars_until(self) -> None:
        s = HTMLInputStream("hello world")
        result = s.charsUntil(" ")
        assert result == "hello"
        assert s.char() == " "

    def test_chars_until_eof(self) -> None:
        s = HTMLInputStream("hello")
        result = s.charsUntil("<")
        assert result == "hello"
        assert s.char() is EOF

    def test_chars_until_empty(self) -> None:
        s = HTMLInputStream("<div>")
        result = s.charsUntil("<")
        assert result == ""
        assert s.char() == "<"

    def test_chars_until_opposite(self) -> None:
        s = HTMLInputStream("   hello")
        result = s.charsUntil(" ", opposite=True)
        assert result == "   "
        assert s.char() == "h"


class TestEncodingDetection:
    def test_utf8_default(self) -> None:
        s = HTMLInputStream("hello")
        assert s.documentEncoding == "utf-8"

    def test_utf8_bom(self) -> None:
        data = b"\xef\xbb\xbfhello"
        s = HTMLInputStream(data)
        assert s.documentEncoding == "utf-8"
        assert s.char() == "h"

    def test_utf16_le_bom(self) -> None:
        data = b"\xff\xfeh\x00e\x00l\x00l\x00o\x00"
        s = HTMLInputStream(data)
        assert s.documentEncoding == "utf-16-le"
        assert s.char() == "h"

    def test_utf16_be_bom(self) -> None:
        data = b"\xfe\xff\x00h\x00e\x00l\x00l\x00o"
        s = HTMLInputStream(data)
        assert s.documentEncoding == "utf-16-be"
        assert s.char() == "h"

    def test_meta_charset(self) -> None:
        data = b'<html><head><meta charset="iso-8859-1"></head></html>'
        s = HTMLInputStream(data)
        assert s.documentEncoding == "iso8859-1"

    def test_override_encoding(self) -> None:
        data = b"hello"
        s = HTMLInputStream(data, override_encoding="ascii")
        assert s.documentEncoding == "ascii"

    def test_transport_encoding(self) -> None:
        data = b"hello"
        s = HTMLInputStream(data, transport_encoding="utf-8")
        assert s.documentEncoding == "utf-8"

    def test_fallback_encoding(self) -> None:
        data = b"\x80\x81\x82"  # no BOM, no meta
        s = HTMLInputStream(data, use_chardet=False)
        assert s.documentEncoding == "windows-1252"


class TestReset:
    def test_reset(self) -> None:
        s = HTMLInputStream("abc")
        s.char()
        s.char()
        s.reset()
        assert s.char() == "a"
        assert s.position == (1, 1)
