"""HTML5 InputStream — encoding detection and character normalization."""

from __future__ import annotations

import codecs
import io
import re
from typing import IO, Optional, Set, Union

from markuptree.constants import spaceCharacters

# Regex to find <meta charset="..."> or <meta http-equiv="Content-Type" content="...charset=...">
_META_CHARSET_RE = re.compile(
    rb"""<meta[^>]+charset\s*=\s*["']?\s*([a-zA-Z0-9_-]+)""",
    re.IGNORECASE,
)

# Number of bytes to sniff for encoding detection.
_SNIFF_SIZE = 1024

# Characters that should trigger a parse error (control characters).
_INVALID_CHARS = frozenset(
    chr(c)
    for c in list(range(0x0001, 0x0009))
    + [0x000B]
    + list(range(0x000E, 0x0020))
    + list(range(0x007F, 0x00A0))
    + list(range(0xFDD0, 0xFDF0))
    + [0xFFFE, 0xFFFF, 0x1FFFE, 0x1FFFF, 0x2FFFE, 0x2FFFF,
       0x3FFFE, 0x3FFFF, 0x4FFFE, 0x4FFFF, 0x5FFFE, 0x5FFFF,
       0x6FFFE, 0x6FFFF, 0x7FFFE, 0x7FFFF, 0x8FFFE, 0x8FFFF,
       0x9FFFE, 0x9FFFF, 0xAFFFE, 0xAFFFF, 0xBFFFE, 0xBFFFF,
       0xCFFFE, 0xCFFFF, 0xDFFFE, 0xDFFFF, 0xEFFFE, 0xEFFFF,
       0xFFFFE, 0xFFFFF, 0x10FFFE, 0x10FFFF]
)

EOF = None


class HTMLInputStream:
    """Read an HTML document, handling encoding detection and character normalization.

    Accepts ``str``, ``bytes``, or file-like objects as input.
    """

    def __init__(
        self,
        source: Union[str, bytes, IO[bytes]],
        override_encoding: Optional[str] = None,
        transport_encoding: Optional[str] = None,
        same_origin_parent_encoding: Optional[str] = None,
        likely_encoding: Optional[str] = None,
        default_encoding: str = "windows-1252",
        use_chardet: bool = True,
    ) -> None:
        self._errors: list[str] = []

        # Determine encoding and get the source as a string.
        if isinstance(source, str):
            self._encoding = "utf-8"
            self._raw = source
        else:
            raw_bytes: bytes
            if isinstance(source, bytes):
                raw_bytes = source
            else:
                raw_bytes = source.read()

            self._encoding = self._detect_encoding(
                raw_bytes,
                override_encoding=override_encoding,
                transport_encoding=transport_encoding,
                same_origin_parent_encoding=same_origin_parent_encoding,
                likely_encoding=likely_encoding,
                default_encoding=default_encoding,
                use_chardet=use_chardet,
            )
            self._raw = self._decode(raw_bytes, self._encoding)

        # Normalize line endings: \r\n and \r → \n.
        self._raw = self._raw.replace("\r\n", "\n").replace("\r", "\n")

        # Replace NULL characters with U+FFFD.
        self._raw = self._raw.replace("\x00", "\uFFFD")

        # State.
        self._pos = 0
        self._line = 1
        self._col = 0
        self._ungot: list[str] = []

    @property
    def documentEncoding(self) -> Optional[str]:
        """Return the encoding used to decode the document."""
        return self._encoding

    @property
    def position(self) -> tuple[int, int]:
        """Return the current (line, column) position."""
        return (self._line, self._col)

    @property
    def errors(self) -> list[str]:
        """Return the list of encoding/normalization errors."""
        return self._errors

    def char(self) -> Optional[str]:
        """Return the next character, or ``None`` at EOF."""
        if self._ungot:
            c = self._ungot.pop()
        elif self._pos >= len(self._raw):
            return EOF
        else:
            c = self._raw[self._pos]
            self._pos += 1

        # Track position.
        if c == "\n":
            self._line += 1
            self._col = 0
        else:
            self._col += 1

        return c

    def charsUntil(self, characters: Union[str, Set[str]], opposite: bool = False) -> str:
        """Read characters until one in *characters* is found (or until one NOT
        in *characters* if *opposite* is True).

        Returns the consumed string (may be empty). Does NOT consume the
        delimiter character.
        """
        if isinstance(characters, str):
            char_set = frozenset(characters)
        else:
            char_set = frozenset(characters)

        result: list[str] = []
        while True:
            if self._ungot:
                c = self._ungot[-1]  # peek
            elif self._pos < len(self._raw):
                c = self._raw[self._pos]
            else:
                break

            if opposite:
                if c in char_set:
                    result.append(self.char())  # type: ignore[arg-type]
                else:
                    break
            else:
                if c not in char_set:
                    result.append(self.char())  # type: ignore[arg-type]
                else:
                    break

        return "".join(result)

    def unget(self, char: Optional[str]) -> None:
        """Push a character back onto the stream."""
        if char is EOF:
            return
        if char is not None:
            self._ungot.append(char)
            # Undo position tracking (approximation).
            if char == "\n":
                self._line -= 1
                # Column is approximate after unget across newlines.
            else:
                self._col -= 1

    def reset(self) -> None:
        """Reset the stream to the beginning."""
        self._pos = 0
        self._line = 1
        self._col = 0
        self._ungot.clear()

    # ------------------------------------------------------------------
    # Encoding detection
    # ------------------------------------------------------------------

    def _detect_encoding(
        self,
        data: bytes,
        override_encoding: Optional[str],
        transport_encoding: Optional[str],
        same_origin_parent_encoding: Optional[str],
        likely_encoding: Optional[str],
        default_encoding: str,
        use_chardet: bool,
    ) -> str:
        # 1. Override encoding.
        if override_encoding:
            return self._resolve_encoding(override_encoding)

        # 2. Transport-layer encoding (e.g., from HTTP Content-Type header).
        if transport_encoding:
            return self._resolve_encoding(transport_encoding)

        # 3. BOM detection.
        bom_enc = self._detect_bom(data)
        if bom_enc:
            return bom_enc

        # 4. <meta charset> sniffing.
        meta_enc = self._sniff_meta_charset(data[:_SNIFF_SIZE])
        if meta_enc:
            return self._resolve_encoding(meta_enc)

        # 5. Same-origin parent encoding.
        if same_origin_parent_encoding:
            return self._resolve_encoding(same_origin_parent_encoding)

        # 6. Likely encoding.
        if likely_encoding:
            return self._resolve_encoding(likely_encoding)

        # 7. chardet (optional).
        if use_chardet:
            try:
                import chardet
                result = chardet.detect(data[:_SNIFF_SIZE * 4])
                if result and result.get("encoding"):
                    return self._resolve_encoding(result["encoding"])
            except ImportError:
                pass

        # 8. Fallback.
        return default_encoding

    @staticmethod
    def _detect_bom(data: bytes) -> Optional[str]:
        if data[:3] == b"\xef\xbb\xbf":
            return "utf-8"
        if data[:2] == b"\xff\xfe":
            return "utf-16-le"
        if data[:2] == b"\xfe\xff":
            return "utf-16-be"
        if data[:4] == b"\x00\x00\xfe\xff":
            return "utf-32-be"
        if data[:4] == b"\xff\xfe\x00\x00":
            return "utf-32-le"
        return None

    @staticmethod
    def _sniff_meta_charset(data: bytes) -> Optional[str]:
        m = _META_CHARSET_RE.search(data)
        if m:
            charset = m.group(1).decode("ascii", errors="ignore").strip()
            try:
                codecs.lookup(charset)
                return charset
            except LookupError:
                return None
        return None

    @staticmethod
    def _resolve_encoding(name: str) -> str:
        """Normalize an encoding name to a Python codec name."""
        try:
            info = codecs.lookup(name)
            return info.name
        except LookupError:
            return "windows-1252"

    @staticmethod
    def _decode(data: bytes, encoding: str) -> str:
        """Decode bytes, stripping BOM if present."""
        # Strip BOM.
        if encoding == "utf-8" and data[:3] == b"\xef\xbb\xbf":
            data = data[3:]
        elif encoding in ("utf-16-le", "utf-16-be") and len(data) >= 2:
            if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
                data = data[2:]

        return data.decode(encoding, errors="replace")


class HTMLBinaryInputStream(HTMLInputStream):
    """Alias for ``HTMLInputStream`` for compatibility."""
    pass
