"""HTML5 Tokenizer — WHATWG state machine implementation."""

from __future__ import annotations

from typing import Any, Dict, Iterator, List, Optional

from markuptree.constants import (
    EOF,
    asciiLetters,
    asciiUppercase,
    entities,
    replacementCharacters,
    spaceCharacters,
    tokenTypes,
)
from markuptree.inputstream import HTMLInputStream

_TokenDict = Dict[str, Any]


class HTMLTokenizer:
    """HTML5 tokenizer consuming an HTMLInputStream and yielding tokens."""

    def __init__(self, stream: HTMLInputStream) -> None:
        self.stream = stream
        self.state: str = "data"
        self.escape_flag = False
        self.last_four_chars = ""
        self.current_token: Optional[_TokenDict] = None
        self.current_attr: Optional[List[Any]] = None  # [name, value]
        self.content_model_flag = "PCDATA"
        self.errors: List[str] = []
        self._pending_tokens: List[_TokenDict] = []
        self._temp_buffer = ""

    def __iter__(self) -> Iterator[_TokenDict]:
        while True:
            tok = self._next_token()
            if tok is not None:
                yield tok
                if tok["type"] == tokenTypes["ParseError"]:
                    continue
                if tok.get("type") == "EOF":
                    return

    def _next_token(self) -> Optional[_TokenDict]:
        """Run the state machine until a token is emitted."""
        if self._pending_tokens:
            return self._pending_tokens.pop(0)

        handler = getattr(self, f"_state_{self.state}", None)
        if handler is None:
            raise RuntimeError(f"Unknown state: {self.state}")
        return handler()

    # -----------------------------------------------------------------------
    # Token helpers
    # -----------------------------------------------------------------------

    def _emit(self, token: _TokenDict) -> _TokenDict:
        return token

    def _emit_char(self, char: str) -> _TokenDict:
        if char and all(c in spaceCharacters for c in char):
            return {"type": tokenTypes["SpaceCharacters"], "data": char}
        return {"type": tokenTypes["Characters"], "data": char}

    def _emit_parse_error(self, msg: str) -> _TokenDict:
        self.errors.append(msg)
        return {"type": tokenTypes["ParseError"], "data": msg}

    def _emit_current_token(self) -> _TokenDict:
        tok = self.current_token
        assert tok is not None
        # Finalize current attribute if any.
        self._finalize_attr()
        self.current_token = None
        return tok

    def _start_attr(self, name: str) -> None:
        self._finalize_attr()
        self.current_attr = [name, ""]

    def _finalize_attr(self) -> None:
        if self.current_attr is None:
            return
        tok = self.current_token
        if tok is not None and "data" in tok:
            attrs = tok["data"]
            name = self.current_attr[0]
            # First attribute wins (HTML5 spec).
            if name not in attrs:
                attrs[name] = self.current_attr[1]
            else:
                self._pending_tokens.insert(
                    0, self._emit_parse_error("duplicate-attribute")
                )
        self.current_attr = None

    # -----------------------------------------------------------------------
    # State: data
    # -----------------------------------------------------------------------

    def _state_data(self) -> Optional[_TokenDict]:
        c = self.stream.char()
        if c is EOF:
            return {"type": "EOF"}
        if c == "&":
            self.state = "entityData"
            return self._next_token()
        if c == "<":
            self.state = "tagOpen"
            return self._next_token()
        if c == "\u0000":
            self._pending_tokens.append(self._emit_parse_error("unexpected-null-character"))
            return self._emit_char("\uFFFD")
        # Batch consecutive text.
        data = c + self.stream.charsUntil({"&", "<", "\u0000"})
        return self._emit_char(data)

    # -----------------------------------------------------------------------
    # State: entityData (character reference in data)
    # -----------------------------------------------------------------------

    def _state_entityData(self) -> Optional[_TokenDict]:
        entity = self._consume_entity()
        self.state = "data"
        if entity:
            return self._emit_char(entity)
        return self._emit_char("&")

    # -----------------------------------------------------------------------
    # State: tagOpen
    # -----------------------------------------------------------------------

    def _state_tagOpen(self) -> Optional[_TokenDict]:
        c = self.stream.char()
        if c is EOF:
            self._pending_tokens.append(self._emit_parse_error("eof-before-tag-name"))
            self.state = "data"
            return self._emit_char("<")
        if c == "!":
            self.state = "markupDeclaration"
            return self._next_token()
        if c == "/":
            self.state = "closeTagOpen"
            return self._next_token()
        if c in asciiLetters:
            self.current_token = {
                "type": tokenTypes["StartTag"],
                "name": c.lower(),
                "data": {},
                "selfClosing": False,
                "selfClosingAcknowledged": False,
            }
            self.state = "tagName"
            return self._next_token()
        if c == "?":
            self._pending_tokens.append(
                self._emit_parse_error("unexpected-question-mark-instead-of-tag-name")
            )
            self.current_token = {"type": tokenTypes["Comment"], "data": ""}
            self.state = "bogusComment"
            self.stream.unget(c)
            return self._next_token()
        self._pending_tokens.append(self._emit_parse_error("invalid-first-character-of-tag-name"))
        self.state = "data"
        return self._emit_char("<" + c)

    # -----------------------------------------------------------------------
    # State: closeTagOpen
    # -----------------------------------------------------------------------

    def _state_closeTagOpen(self) -> Optional[_TokenDict]:
        c = self.stream.char()
        if c is EOF:
            self._pending_tokens.append(self._emit_parse_error("eof-after-solidus"))
            self.state = "data"
            return self._emit_char("</")
        if c in asciiLetters:
            self.current_token = {
                "type": tokenTypes["EndTag"],
                "name": c.lower(),
                "data": {},
                "selfClosing": False,
            }
            self.state = "tagName"
            return self._next_token()
        if c == ">":
            self._pending_tokens.append(self._emit_parse_error("missing-end-tag-name"))
            self.state = "data"
            return self._next_token()
        self._pending_tokens.append(
            self._emit_parse_error("invalid-first-character-of-tag-name")
        )
        self.current_token = {"type": tokenTypes["Comment"], "data": ""}
        self.state = "bogusComment"
        self.stream.unget(c)
        return self._next_token()

    # -----------------------------------------------------------------------
    # State: tagName
    # -----------------------------------------------------------------------

    def _state_tagName(self) -> Optional[_TokenDict]:
        c = self.stream.char()
        if c is EOF:
            self._pending_tokens.append({"type": "EOF"})
            return self._emit_parse_error("eof-in-tag")
        if c in spaceCharacters:
            self.state = "beforeAttrName"
            return self._next_token()
        if c == "/":
            self.state = "selfClosingStartTag"
            return self._next_token()
        if c == ">":
            self.state = "data"
            return self._emit_current_token()
        if c in asciiUppercase:
            assert self.current_token is not None
            self.current_token["name"] += c.lower()
            return self._next_token()
        if c == "\u0000":
            self._pending_tokens.append(self._emit_parse_error("unexpected-null-character"))
            assert self.current_token is not None
            self.current_token["name"] += "\uFFFD"
            return self._next_token()
        assert self.current_token is not None
        self.current_token["name"] += c
        return self._next_token()

    # -----------------------------------------------------------------------
    # State: beforeAttrName
    # -----------------------------------------------------------------------

    def _state_beforeAttrName(self) -> Optional[_TokenDict]:
        c = self.stream.char()
        if c is EOF:
            self._pending_tokens.append({"type": "EOF"})
            return self._emit_parse_error("eof-in-tag")
        if c in spaceCharacters:
            return self._next_token()
        if c in ("/", ">"):
            self.stream.unget(c)
            self.state = "afterAttrName"
            return self._next_token()
        if c == "=":
            self._pending_tokens.append(
                self._emit_parse_error("unexpected-equals-sign-before-attribute-name")
            )
            self._start_attr(c)
            self.state = "attrName"
            return self._next_token()
        self._start_attr("")
        self.stream.unget(c)
        self.state = "attrName"
        return self._next_token()

    # -----------------------------------------------------------------------
    # State: attrName
    # -----------------------------------------------------------------------

    def _state_attrName(self) -> Optional[_TokenDict]:
        c = self.stream.char()
        if c is EOF or c in spaceCharacters:
            self.state = "afterAttrName"
            if c is EOF:
                self.stream.unget(c)
            return self._next_token()
        if c in ("/", ">"):
            self.stream.unget(c)
            self.state = "afterAttrName"
            return self._next_token()
        if c == "=":
            self.state = "beforeAttrValue"
            return self._next_token()
        if c in asciiUppercase:
            assert self.current_attr is not None
            self.current_attr[0] += c.lower()
            return self._next_token()
        if c == "\u0000":
            self._pending_tokens.append(self._emit_parse_error("unexpected-null-character"))
            assert self.current_attr is not None
            self.current_attr[0] += "\uFFFD"
            return self._next_token()
        assert self.current_attr is not None
        self.current_attr[0] += c
        return self._next_token()

    # -----------------------------------------------------------------------
    # State: afterAttrName
    # -----------------------------------------------------------------------

    def _state_afterAttrName(self) -> Optional[_TokenDict]:
        c = self.stream.char()
        if c is EOF:
            self._pending_tokens.append({"type": "EOF"})
            return self._emit_parse_error("eof-in-tag")
        if c in spaceCharacters:
            return self._next_token()
        if c == "/":
            self.state = "selfClosingStartTag"
            return self._next_token()
        if c == "=":
            self.state = "beforeAttrValue"
            return self._next_token()
        if c == ">":
            self.state = "data"
            return self._emit_current_token()
        self._start_attr("")
        self.stream.unget(c)
        self.state = "attrName"
        return self._next_token()

    # -----------------------------------------------------------------------
    # State: beforeAttrValue
    # -----------------------------------------------------------------------

    def _state_beforeAttrValue(self) -> Optional[_TokenDict]:
        c = self.stream.char()
        if c is EOF:
            self._pending_tokens.append({"type": "EOF"})
            return self._emit_parse_error("eof-in-tag")
        if c in spaceCharacters:
            return self._next_token()
        if c == '"':
            self.state = "attrValueDQ"
            return self._next_token()
        if c == "'":
            self.state = "attrValueSQ"
            return self._next_token()
        if c == ">":
            self._pending_tokens.append(self._emit_parse_error("missing-attribute-value"))
            self.state = "data"
            return self._emit_current_token()
        self.stream.unget(c)
        self.state = "attrValueUnquoted"
        return self._next_token()

    # -----------------------------------------------------------------------
    # State: attrValueDQ (double-quoted)
    # -----------------------------------------------------------------------

    def _state_attrValueDQ(self) -> Optional[_TokenDict]:
        c = self.stream.char()
        if c is EOF:
            self._pending_tokens.append({"type": "EOF"})
            return self._emit_parse_error("eof-in-tag")
        if c == '"':
            self.state = "afterAttrValueQuoted"
            return self._next_token()
        if c == "&":
            data = self._consume_entity(additional_allowed='"')
            assert self.current_attr is not None
            self.current_attr[1] += data if data else "&"
            return self._next_token()
        if c == "\u0000":
            self._pending_tokens.append(self._emit_parse_error("unexpected-null-character"))
            assert self.current_attr is not None
            self.current_attr[1] += "\uFFFD"
            return self._next_token()
        assert self.current_attr is not None
        self.current_attr[1] += c + self.stream.charsUntil({'"', "&", "\u0000"})
        return self._next_token()

    # -----------------------------------------------------------------------
    # State: attrValueSQ (single-quoted)
    # -----------------------------------------------------------------------

    def _state_attrValueSQ(self) -> Optional[_TokenDict]:
        c = self.stream.char()
        if c is EOF:
            self._pending_tokens.append({"type": "EOF"})
            return self._emit_parse_error("eof-in-tag")
        if c == "'":
            self.state = "afterAttrValueQuoted"
            return self._next_token()
        if c == "&":
            data = self._consume_entity(additional_allowed="'")
            assert self.current_attr is not None
            self.current_attr[1] += data if data else "&"
            return self._next_token()
        if c == "\u0000":
            self._pending_tokens.append(self._emit_parse_error("unexpected-null-character"))
            assert self.current_attr is not None
            self.current_attr[1] += "\uFFFD"
            return self._next_token()
        assert self.current_attr is not None
        self.current_attr[1] += c + self.stream.charsUntil({"'", "&", "\u0000"})
        return self._next_token()

    # -----------------------------------------------------------------------
    # State: attrValueUnquoted
    # -----------------------------------------------------------------------

    def _state_attrValueUnquoted(self) -> Optional[_TokenDict]:
        c = self.stream.char()
        if c is EOF:
            self._pending_tokens.append({"type": "EOF"})
            return self._emit_parse_error("eof-in-tag")
        if c in spaceCharacters:
            self.state = "beforeAttrName"
            return self._next_token()
        if c == "&":
            data = self._consume_entity(additional_allowed=">")
            assert self.current_attr is not None
            self.current_attr[1] += data if data else "&"
            return self._next_token()
        if c == ">":
            self.state = "data"
            return self._emit_current_token()
        if c == "\u0000":
            self._pending_tokens.append(self._emit_parse_error("unexpected-null-character"))
            assert self.current_attr is not None
            self.current_attr[1] += "\uFFFD"
            return self._next_token()
        assert self.current_attr is not None
        self.current_attr[1] += c + self.stream.charsUntil(
            spaceCharacters | {"&", ">", "\u0000", '"', "'", "<", "=", "`"}
        )
        return self._next_token()

    # -----------------------------------------------------------------------
    # State: afterAttrValueQuoted
    # -----------------------------------------------------------------------

    def _state_afterAttrValueQuoted(self) -> Optional[_TokenDict]:
        c = self.stream.char()
        if c is EOF:
            self._pending_tokens.append({"type": "EOF"})
            return self._emit_parse_error("eof-in-tag")
        if c in spaceCharacters:
            self.state = "beforeAttrName"
            return self._next_token()
        if c == "/":
            self.state = "selfClosingStartTag"
            return self._next_token()
        if c == ">":
            self.state = "data"
            return self._emit_current_token()
        self._pending_tokens.append(
            self._emit_parse_error("missing-whitespace-between-attributes")
        )
        self.stream.unget(c)
        self.state = "beforeAttrName"
        return self._next_token()

    # -----------------------------------------------------------------------
    # State: selfClosingStartTag
    # -----------------------------------------------------------------------

    def _state_selfClosingStartTag(self) -> Optional[_TokenDict]:
        c = self.stream.char()
        if c is EOF:
            self._pending_tokens.append({"type": "EOF"})
            return self._emit_parse_error("eof-in-tag")
        if c == ">":
            assert self.current_token is not None
            self.current_token["selfClosing"] = True
            self.state = "data"
            return self._emit_current_token()
        self._pending_tokens.append(
            self._emit_parse_error("unexpected-solidus-in-tag")
        )
        self.stream.unget(c)
        self.state = "beforeAttrName"
        return self._next_token()

    # -----------------------------------------------------------------------
    # State: bogusComment
    # -----------------------------------------------------------------------

    def _state_bogusComment(self) -> Optional[_TokenDict]:
        assert self.current_token is not None
        data = self.stream.charsUntil(">")
        self.current_token["data"] += data
        self.stream.char()  # consume the ">"
        self.state = "data"
        return self._emit_current_token()

    # -----------------------------------------------------------------------
    # State: markupDeclaration
    # -----------------------------------------------------------------------

    def _state_markupDeclaration(self) -> Optional[_TokenDict]:
        c1 = self.stream.char()
        c2 = self.stream.char()
        if c1 == "-" and c2 == "-":
            self.current_token = {"type": tokenTypes["Comment"], "data": ""}
            self.state = "commentStart"
            return self._next_token()
        # Check for DOCTYPE.
        if c1 is not None and c2 is not None:
            chars_read = [c1, c2]
            for _ in range(5):
                ch = self.stream.char()
                if ch is EOF:
                    break
                chars_read.append(ch)
            word = "".join(c for c in chars_read if c is not None)
            if word.upper() == "DOCTYPE":
                self.current_token = {
                    "type": tokenTypes["Doctype"],
                    "name": "",
                    "publicId": None,
                    "systemId": None,
                    "correct": True,
                }
                self.state = "doctype"
                return self._next_token()
            # Check for CDATA.
            if word == "[CDATA[":
                self.state = "cdataSection"
                return self._next_token()
            # Unknown — bogus comment.
            for ch in reversed(chars_read[2:]):
                if ch is not None:
                    self.stream.unget(ch)
            self._pending_tokens.append(
                self._emit_parse_error("incorrectly-opened-comment")
            )
            self.current_token = {"type": tokenTypes["Comment"], "data": ""}
            self.state = "bogusComment"
            return self._next_token()
        # EOF or incomplete.
        if c2 is not None:
            self.stream.unget(c2)
        if c1 is not None:
            self.stream.unget(c1)
        self._pending_tokens.append(
            self._emit_parse_error("incorrectly-opened-comment")
        )
        self.current_token = {"type": tokenTypes["Comment"], "data": ""}
        self.state = "bogusComment"
        return self._next_token()

    # -----------------------------------------------------------------------
    # Comment states
    # -----------------------------------------------------------------------

    def _state_commentStart(self) -> Optional[_TokenDict]:
        c = self.stream.char()
        if c is EOF:
            self._pending_tokens.append(self._emit_current_token())
            self._pending_tokens.append({"type": "EOF"})
            self.state = "data"
            return self._emit_parse_error("eof-in-comment")
        if c == "-":
            self.state = "commentStartDash"
            return self._next_token()
        if c == ">":
            self._pending_tokens.append(self._emit_parse_error("abrupt-closing-of-empty-comment"))
            self.state = "data"
            return self._emit_current_token()
        self.stream.unget(c)
        self.state = "comment"
        return self._next_token()

    def _state_commentStartDash(self) -> Optional[_TokenDict]:
        c = self.stream.char()
        if c is EOF:
            self._pending_tokens.append(self._emit_current_token())
            self._pending_tokens.append({"type": "EOF"})
            self.state = "data"
            return self._emit_parse_error("eof-in-comment")
        if c == "-":
            self.state = "commentEnd"
            return self._next_token()
        if c == ">":
            self._pending_tokens.append(self._emit_parse_error("abrupt-closing-of-empty-comment"))
            self.state = "data"
            return self._emit_current_token()
        assert self.current_token is not None
        self.current_token["data"] += "-"
        self.stream.unget(c)
        self.state = "comment"
        return self._next_token()

    def _state_comment(self) -> Optional[_TokenDict]:
        c = self.stream.char()
        if c is EOF:
            self._pending_tokens.append(self._emit_current_token())
            self._pending_tokens.append({"type": "EOF"})
            self.state = "data"
            return self._emit_parse_error("eof-in-comment")
        if c == "-":
            self.state = "commentEndDash"
            return self._next_token()
        if c == "\u0000":
            self._pending_tokens.append(self._emit_parse_error("unexpected-null-character"))
            assert self.current_token is not None
            self.current_token["data"] += "\uFFFD"
            return self._next_token()
        assert self.current_token is not None
        self.current_token["data"] += c + self.stream.charsUntil({"-", "\u0000"})
        return self._next_token()

    def _state_commentEndDash(self) -> Optional[_TokenDict]:
        c = self.stream.char()
        if c is EOF:
            self._pending_tokens.append(self._emit_current_token())
            self._pending_tokens.append({"type": "EOF"})
            self.state = "data"
            return self._emit_parse_error("eof-in-comment")
        if c == "-":
            self.state = "commentEnd"
            return self._next_token()
        assert self.current_token is not None
        self.current_token["data"] += "-"
        self.stream.unget(c)
        self.state = "comment"
        return self._next_token()

    def _state_commentEnd(self) -> Optional[_TokenDict]:
        c = self.stream.char()
        if c is EOF:
            self._pending_tokens.append(self._emit_current_token())
            self._pending_tokens.append({"type": "EOF"})
            self.state = "data"
            return self._emit_parse_error("eof-in-comment")
        if c == ">":
            self.state = "data"
            return self._emit_current_token()
        if c == "-":
            assert self.current_token is not None
            self.current_token["data"] += "-"
            return self._next_token()
        if c == "!":
            self._pending_tokens.append(
                self._emit_parse_error("incorrectly-closed-comment")
            )
            self.state = "commentEndBang"
            return self._next_token()
        assert self.current_token is not None
        self.current_token["data"] += "--"
        self.stream.unget(c)
        self.state = "comment"
        return self._next_token()

    def _state_commentEndBang(self) -> Optional[_TokenDict]:
        c = self.stream.char()
        if c is EOF:
            self._pending_tokens.append(self._emit_current_token())
            self._pending_tokens.append({"type": "EOF"})
            self.state = "data"
            return self._emit_parse_error("eof-in-comment")
        if c == "-":
            assert self.current_token is not None
            self.current_token["data"] += "--!"
            self.state = "commentEndDash"
            return self._next_token()
        if c == ">":
            self.state = "data"
            return self._emit_current_token()
        assert self.current_token is not None
        self.current_token["data"] += "--!"
        self.stream.unget(c)
        self.state = "comment"
        return self._next_token()

    # -----------------------------------------------------------------------
    # DOCTYPE states (simplified)
    # -----------------------------------------------------------------------

    def _state_doctype(self) -> Optional[_TokenDict]:
        c = self.stream.char()
        if c is EOF:
            assert self.current_token is not None
            self.current_token["correct"] = False
            self._pending_tokens.append(self._emit_current_token())
            self._pending_tokens.append({"type": "EOF"})
            self.state = "data"
            return self._emit_parse_error("eof-in-doctype")
        if c in spaceCharacters:
            self.state = "beforeDoctypeName"
            return self._next_token()
        if c == ">":
            self.stream.unget(c)
            self.state = "beforeDoctypeName"
            return self._next_token()
        self._pending_tokens.append(
            self._emit_parse_error("missing-whitespace-before-doctype-name")
        )
        self.stream.unget(c)
        self.state = "beforeDoctypeName"
        return self._next_token()

    def _state_beforeDoctypeName(self) -> Optional[_TokenDict]:
        c = self.stream.char()
        if c is EOF:
            assert self.current_token is not None
            self.current_token["correct"] = False
            self._pending_tokens.append(self._emit_current_token())
            self._pending_tokens.append({"type": "EOF"})
            self.state = "data"
            return self._emit_parse_error("eof-in-doctype")
        if c in spaceCharacters:
            return self._next_token()
        if c == ">":
            self._pending_tokens.append(self._emit_parse_error("missing-doctype-name"))
            assert self.current_token is not None
            self.current_token["correct"] = False
            self.state = "data"
            return self._emit_current_token()
        if c in asciiUppercase:
            assert self.current_token is not None
            self.current_token["name"] = c.lower()
        else:
            assert self.current_token is not None
            self.current_token["name"] = c
        self.state = "doctypeName"
        return self._next_token()

    def _state_doctypeName(self) -> Optional[_TokenDict]:
        c = self.stream.char()
        if c is EOF:
            assert self.current_token is not None
            self.current_token["correct"] = False
            self._pending_tokens.append(self._emit_current_token())
            self._pending_tokens.append({"type": "EOF"})
            self.state = "data"
            return self._emit_parse_error("eof-in-doctype")
        if c in spaceCharacters:
            self.state = "afterDoctypeName"
            return self._next_token()
        if c == ">":
            self.state = "data"
            return self._emit_current_token()
        if c in asciiUppercase:
            assert self.current_token is not None
            self.current_token["name"] += c.lower()
        else:
            assert self.current_token is not None
            self.current_token["name"] += c
        return self._next_token()

    def _state_afterDoctypeName(self) -> Optional[_TokenDict]:
        c = self.stream.char()
        if c is EOF:
            assert self.current_token is not None
            self.current_token["correct"] = False
            self._pending_tokens.append(self._emit_current_token())
            self._pending_tokens.append({"type": "EOF"})
            self.state = "data"
            return self._emit_parse_error("eof-in-doctype")
        if c in spaceCharacters:
            return self._next_token()
        if c == ">":
            self.state = "data"
            return self._emit_current_token()
        # Simplified: skip PUBLIC/SYSTEM identifiers.
        # Consume until >.
        self.stream.charsUntil(">")
        self.stream.char()  # consume >
        self.state = "data"
        return self._emit_current_token()

    # -----------------------------------------------------------------------
    # CDATA section state
    # -----------------------------------------------------------------------

    def _state_cdataSection(self) -> Optional[_TokenDict]:
        data = []
        while True:
            c = self.stream.char()
            if c is EOF:
                break
            if c == "]":
                c2 = self.stream.char()
                if c2 == "]":
                    c3 = self.stream.char()
                    if c3 == ">":
                        break
                    data.append("]]")
                    if c3 is not None:
                        self.stream.unget(c3)
                else:
                    data.append("]")
                    if c2 is not None:
                        self.stream.unget(c2)
            else:
                data.append(c)
        text = "".join(data)
        self.state = "data"
        if text:
            return self._emit_char(text)
        return self._next_token()

    # -----------------------------------------------------------------------
    # RCDATA state
    # -----------------------------------------------------------------------

    def _state_rcdata(self) -> Optional[_TokenDict]:
        c = self.stream.char()
        if c is EOF:
            return {"type": "EOF"}
        if c == "&":
            entity = self._consume_entity()
            return self._emit_char(entity if entity else "&")
        if c == "<":
            self.state = "rcdataLessThan"
            return self._next_token()
        if c == "\u0000":
            self._pending_tokens.append(self._emit_parse_error("unexpected-null-character"))
            return self._emit_char("\uFFFD")
        return self._emit_char(c + self.stream.charsUntil({"&", "<", "\u0000"}))

    def _state_rcdataLessThan(self) -> Optional[_TokenDict]:
        c = self.stream.char()
        if c == "/":
            self._temp_buffer = ""
            self.state = "rcdataEndTagOpen"
            return self._next_token()
        self.state = "rcdata"
        self.stream.unget(c)
        return self._emit_char("<")

    def _state_rcdataEndTagOpen(self) -> Optional[_TokenDict]:
        c = self.stream.char()
        if c is not None and c in asciiLetters:
            self.current_token = {
                "type": tokenTypes["EndTag"],
                "name": c.lower(),
                "data": {},
                "selfClosing": False,
            }
            self._temp_buffer += c
            self.state = "rcdataEndTagName"
            return self._next_token()
        self.state = "rcdata"
        self.stream.unget(c)
        return self._emit_char("</")

    def _state_rcdataEndTagName(self) -> Optional[_TokenDict]:
        c = self.stream.char()
        if c in spaceCharacters:
            self.state = "beforeAttrName"
            return self._next_token()
        if c == "/":
            self.state = "selfClosingStartTag"
            return self._next_token()
        if c == ">":
            self.state = "data"
            return self._emit_current_token()
        if c is not None and c in asciiLetters:
            assert self.current_token is not None
            self.current_token["name"] += c.lower()
            self._temp_buffer += c
            return self._next_token()
        self.state = "rcdata"
        self.stream.unget(c)
        return self._emit_char("</" + self._temp_buffer)

    # -----------------------------------------------------------------------
    # RAWTEXT state
    # -----------------------------------------------------------------------

    def _state_rawtext(self) -> Optional[_TokenDict]:
        c = self.stream.char()
        if c is EOF:
            return {"type": "EOF"}
        if c == "<":
            self.state = "rawtextLessThan"
            return self._next_token()
        if c == "\u0000":
            self._pending_tokens.append(self._emit_parse_error("unexpected-null-character"))
            return self._emit_char("\uFFFD")
        return self._emit_char(c + self.stream.charsUntil({"<", "\u0000"}))

    def _state_rawtextLessThan(self) -> Optional[_TokenDict]:
        c = self.stream.char()
        if c == "/":
            self._temp_buffer = ""
            self.state = "rawtextEndTagOpen"
            return self._next_token()
        self.state = "rawtext"
        self.stream.unget(c)
        return self._emit_char("<")

    def _state_rawtextEndTagOpen(self) -> Optional[_TokenDict]:
        c = self.stream.char()
        if c is not None and c in asciiLetters:
            self.current_token = {
                "type": tokenTypes["EndTag"],
                "name": c.lower(),
                "data": {},
                "selfClosing": False,
            }
            self._temp_buffer += c
            self.state = "rawtextEndTagName"
            return self._next_token()
        self.state = "rawtext"
        self.stream.unget(c)
        return self._emit_char("</")

    def _state_rawtextEndTagName(self) -> Optional[_TokenDict]:
        c = self.stream.char()
        if c in spaceCharacters:
            self.state = "beforeAttrName"
            return self._next_token()
        if c == "/":
            self.state = "selfClosingStartTag"
            return self._next_token()
        if c == ">":
            self.state = "data"
            return self._emit_current_token()
        if c is not None and c in asciiLetters:
            assert self.current_token is not None
            self.current_token["name"] += c.lower()
            self._temp_buffer += c
            return self._next_token()
        self.state = "rawtext"
        self.stream.unget(c)
        return self._emit_char("</" + self._temp_buffer)

    # -----------------------------------------------------------------------
    # PLAINTEXT state
    # -----------------------------------------------------------------------

    def _state_plaintext(self) -> Optional[_TokenDict]:
        c = self.stream.char()
        if c is EOF:
            return {"type": "EOF"}
        if c == "\u0000":
            self._pending_tokens.append(self._emit_parse_error("unexpected-null-character"))
            return self._emit_char("\uFFFD")
        return self._emit_char(c + self.stream.charsUntil({"\u0000"}))

    # -----------------------------------------------------------------------
    # Character reference consumption
    # -----------------------------------------------------------------------

    def _consume_entity(self, additional_allowed: Optional[str] = None) -> Optional[str]:
        """Consume a character reference and return the replacement string."""
        c = self.stream.char()
        if c is EOF or c in spaceCharacters or c == "<" or c == "&" or (
            additional_allowed is not None and c == additional_allowed
        ):
            self.stream.unget(c)
            return None

        if c == "#":
            return self._consume_numeric_entity()

        # Named entity.
        self.stream.unget(c)
        return self._consume_named_entity()

    def _consume_numeric_entity(self) -> str:
        """Consume &#...; or &#x...; numeric character reference."""
        c = self.stream.char()
        if c is EOF:
            self._pending_tokens.append(
                self._emit_parse_error("absence-of-digits-in-numeric-character-reference")
            )
            return "&#"

        is_hex = c in ("x", "X")
        if not is_hex:
            self.stream.unget(c)

        valid_digits = "0123456789abcdefABCDEF" if is_hex else "0123456789"
        buf = ""
        while True:
            ch = self.stream.char()
            if ch is EOF:
                break
            if ch in valid_digits:
                buf += ch
            elif ch == ";":
                break
            else:
                self.stream.unget(ch)
                self._pending_tokens.append(
                    self._emit_parse_error("missing-semicolon-after-character-reference")
                )
                break

        if not buf:
            self._pending_tokens.append(
                self._emit_parse_error("absence-of-digits-in-numeric-character-reference")
            )
            return ("&#x" if is_hex else "&#")

        code_point = int(buf, 16) if is_hex else int(buf, 10)

        if code_point in replacementCharacters:
            self._pending_tokens.append(
                self._emit_parse_error("character-reference-outside-unicode-range")
            )
            return replacementCharacters[code_point]

        if code_point == 0:
            self._pending_tokens.append(self._emit_parse_error("null-character-reference"))
            return "\uFFFD"

        if code_point > 0x10FFFF:
            self._pending_tokens.append(
                self._emit_parse_error("character-reference-outside-unicode-range")
            )
            return "\uFFFD"

        if 0xD800 <= code_point <= 0xDFFF:
            self._pending_tokens.append(
                self._emit_parse_error("surrogate-character-reference")
            )
            return "\uFFFD"

        return chr(code_point)

    def _consume_named_entity(self) -> Optional[str]:
        """Consume a named character reference like &amp; or &lt;."""
        buf = ""
        last_match = ""
        last_match_value = ""

        for _ in range(64):  # max entity name length
            c = self.stream.char()
            if c is EOF:
                break
            buf += c
            if buf in entities:
                last_match = buf
                last_match_value = entities[buf]
            if c == ";":
                break
            # If no possible match could start with this prefix, stop.
            if not any(k.startswith(buf) for k in entities if len(k) > len(buf)):
                if buf not in entities:
                    break

        if last_match:
            # Unget chars after the match.
            extra = buf[len(last_match):]
            for ch in reversed(extra):
                self.stream.unget(ch)
            if not last_match.endswith(";"):
                self._pending_tokens.append(
                    self._emit_parse_error("missing-semicolon-after-character-reference")
                )
            return last_match_value

        # No match — unget everything.
        for ch in reversed(buf):
            self.stream.unget(ch)
        return None
