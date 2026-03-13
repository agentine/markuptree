# markuptree

A WHATWG HTML5-compliant parser and zero-dependency drop-in replacement for [html5lib](https://github.com/html5lib/html5lib-python).

## Why markuptree

[html5lib](https://github.com/html5lib/html5lib-python) is effectively abandoned — its last release was June 2020, it still depends on `six` (a Python 2 compatibility layer) and `webencodings` (unnecessary with modern stdlib), and it has 95 open issues with no active triage. Despite this, it receives 30 million monthly PyPI downloads because nothing else implements the full WHATWG HTML5 parsing algorithm in pure Python.

markuptree fixes that:

- **WHATWG HTML5-compliant** — implements the full HTML5 tokenization and tree construction algorithm
- **Zero required dependencies** — Python 3.9+ only; drops `six` and replaces `webencodings` with stdlib `codecs`
- **Drop-in replacement** — `import markuptree as html5lib` works without changing any other code
- **Modern sanitizer** — not deprecated, with safe defaults and URI scheme allow-listing
- **Full type annotations** — complete type stubs for IDE support
- **Python 3.9+** — 3.9, 3.10, 3.11, 3.12, 3.13

Optional extras: `pip install markuptree[lxml]` for lxml backend, `pip install markuptree[chardet]` for chardet encoding detection, or `pip install markuptree[all]` for both.

## Installation

```bash
pip install markuptree
```

## Quick Start

```python
import markuptree

# Parse a full HTML document
doc = markuptree.parse("<html><body><p>Hello <b>world</b></p></body></html>")

# Parse an HTML fragment
fragment = markuptree.parseFragment("<p>Hello</p><p>World</p>")

# Serialize a tree back to HTML
html = markuptree.serialize(doc, tree="etree")

# Use HTMLParser directly for access to errors and encoding
parser = markuptree.HTMLParser(tree="etree")
doc = parser.parse("<p>Hello</p>")
print(parser.errors)            # list of (message,) tuples
print(parser.documentEncoding)  # e.g. "utf-8"
```

## Top-Level API

### `parse(doc, treebuilder="etree", namespaceHTMLElements=True, **kwargs)`

Parse a full HTML document and return a tree. `doc` may be a `str`, `bytes`, or file-like object. `treebuilder` selects the backend (`"etree"`, `"dom"`, or `"lxml"`). When `namespaceHTMLElements=True` (default), HTML elements carry the XHTML namespace URI.

```python
doc = markuptree.parse("<p>hello</p>")
doc = markuptree.parse(b"<p>caf\xc3\xa9</p>")  # bytes decoded automatically
```

### `parseFragment(doc, container="div", treebuilder="etree", namespaceHTMLElements=True, **kwargs)`

Parse an HTML fragment and return a list of nodes. The `container` element provides the parsing context (important for certain elements like `<td>`).

```python
nodes = markuptree.parseFragment("<li>one</li><li>two</li>", container="ul")
```

### `getTreeBuilder(treeType, implementation=None, **kwargs)`

Return a `TreeBuilder` class for the named backend. Pass the class to `HTMLParser(tree=...)` or use it directly.

```python
TB = markuptree.getTreeBuilder("etree")
```

### `getTreeWalker(treeType, implementation=None, **kwargs)`

Return a `TreeWalker` class for the named backend.

```python
Walker = markuptree.getTreeWalker("etree")
walker = Walker(doc)
for token in walker:
    print(token)
```

### `serialize(input, tree="etree", encoding=None, **serializer_opts)`

Convenience function: walk a tree and return an HTML string. All `HTMLSerializer` options can be passed as keyword arguments.

```python
html = markuptree.serialize(doc, tree="etree", omit_optional_tags=False)
```

### `HTMLParser`

```python
class HTMLParser:
    def __init__(
        self,
        tree=None,            # treebuilder name or class; defaults to "etree"
        strict=False,         # raise ParseError on any parse error
        namespaceHTMLElements=True,
        debug=False,
    )
    def parse(self, stream, *args, **kwargs) -> tree
    def parseFragment(self, stream, *args, container="div", scripting=False, **kwargs) -> list
    @property
    def documentEncoding(self) -> Optional[str]
    @property
    def errors(self) -> list[tuple]  # list of (message,) tuples
```

Setting `strict=True` causes `ParseError` to be raised immediately on the first parse error instead of collecting errors and continuing.

## Tree Builders

Tree builders construct a tree from the token stream. The tree format depends on the backend.

| Backend | `getTreeBuilder()` name | Underlying library |
|---------|------------------------|--------------------|
| etree | `"etree"` | `xml.etree.ElementTree` (stdlib, default) |
| dom | `"dom"` | `xml.dom.minidom` (stdlib) |
| lxml | `"lxml"` | `lxml.etree` (requires `pip install markuptree[lxml]`) |

```python
# Default etree backend
doc = markuptree.parse("<p>hello</p>")

# DOM backend
doc = markuptree.parse("<p>hello</p>", treebuilder="dom")

# lxml backend (install lxml first)
doc = markuptree.parse("<p>hello</p>", treebuilder="lxml")

# Get the builder class directly
TB = markuptree.getTreeBuilder("etree")
parser = markuptree.HTMLParser(tree=TB)
```

## Tree Walkers

Tree walkers traverse a parsed tree and yield serializer tokens. There are four backends:

| Backend | `getTreeWalker()` name | Notes |
|---------|------------------------|-------|
| etree | `"etree"` | Works with etree and lxml trees |
| dom | `"dom"` | Works with minidom trees |
| lxml | `"lxml"` | Optimized for lxml trees |
| genshi | `"genshi"` | Yields Genshi event stream |

```python
Walker = markuptree.getTreeWalker("etree")
walker = Walker(doc)

# Iterate tokens directly
for token in walker:
    print(token["type"], token.get("name", ""))

# Or feed into the serializer
from markuptree.serializer import HTMLSerializer
html = HTMLSerializer().render(Walker(doc))
```

Each token is a plain dict. See the [Token format](#token-format) section for the full schema.

## Serializer

`HTMLSerializer` converts a token stream back to HTML. It accepts 14 options:

```python
from markuptree.serializer import HTMLSerializer

Walker = markuptree.getTreeWalker("etree")
s = HTMLSerializer(
    omit_optional_tags=True,
    quote_attr_values="always",
    minimize_boolean_attributes=True,
    alphabetical_attributes=True,
    inject_meta_charset=True,
)

# Generator — yields string fragments
for chunk in s.serialize(Walker(doc)):
    sys.stdout.write(chunk)

# Eager — returns the full string
html = s.render(Walker(doc))
```

### Serializer Options

| Option | Default | Description |
|--------|---------|-------------|
| `quote_attr_values` | `"legacy"` | `"legacy"` (quote when required) or `"always"` |
| `quote_char` | `'"'` | Preferred quote character for attributes |
| `use_best_quote_char` | `True` | Choose `'` or `"` to minimize escaping |
| `omit_optional_tags` | `True` | Omit optional start/end tags per HTML5 spec |
| `minimize_boolean_attributes` | `True` | Emit `disabled` instead of `disabled="disabled"` |
| `use_trailing_solidus` | `False` | Emit `<br />` instead of `<br>` |
| `space_before_trailing_solidus` | `True` | Emit space before `/>` |
| `escape_lt_in_attrs` | `False` | Escape `<` in attribute values |
| `escape_rcdata` | `False` | Escape `<`/`>` inside RCDATA elements (`<title>`, `<textarea>`) |
| `resolve_entities` | `True` | Resolve named character entities to Unicode |
| `alphabetical_attributes` | `False` | Sort attributes alphabetically |
| `inject_meta_charset` | `True` | Inject or update `<meta charset>` |
| `strip_whitespace` | `False` | Collapse inter-element whitespace |
| `sanitize` | `False` | Strip unsafe elements and attributes (see Filters) |

## Filters

Filters sit between a tree walker and the serializer, transforming the token stream. They can be composed.

```python
from markuptree.treewalkers.etree import TreeWalker
from markuptree.filters.sanitizer import Filter as SanitizerFilter
from markuptree.filters.whitespace import Filter as WhitespaceFilter
from markuptree.serializer import HTMLSerializer

walker = TreeWalker(doc)
pipeline = WhitespaceFilter(SanitizerFilter(walker))
html = HTMLSerializer(omit_optional_tags=False).render(pipeline)
```

| Filter module | Class | Description |
|---------------|-------|-------------|
| `filters.base` | `Filter` | Passthrough base class for custom filters |
| `filters.alphabeticalattributes` | `Filter` | Sort element attributes A–Z |
| `filters.inject_meta_charset` | `Filter(source, encoding)` | Inject or replace `<meta charset>` |
| `filters.whitespace` | `Filter` | Collapse inter-element whitespace (preserves `<pre>`) |
| `filters.optionaltags` | `Filter` | Remove optional start/end tags |
| `filters.sanitizer` | `Filter(source, allowed_elements, allowed_attrs)` | Strip unsafe elements, attributes, and URI schemes |
| `filters.lint` | `Filter(source, require_matching_tags=True)` | Warn on void/non-void tag misuse |

## Security

markuptree includes several XSS protections:

**Comment sanitization** — `-->` sequences inside HTML comments are rewritten to `- ->` so comment content cannot break out of the comment node.

**Script injection prevention** — `</script>` and `</style>` sequences inside CDATA elements (script/style text content) are escaped as `<\/script>` and `<\/style>`.

**data: URI blocking** — the sanitizer filter rejects `data:` URIs in href, src, action, and other URI-bearing attributes. Only `http`, `https`, `mailto`, `ftp`, `ftps`, and `tel` schemes are permitted.

**RCDATA/RAWTEXT enforcement** — content inside `<title>` and `<textarea>` (RCDATA) and `<script>`/`<style>` (RAWTEXT) is handled per the WHATWG state machine, preventing content from being interpreted as markup.

**Strict mode** — pass `strict=True` to `HTMLParser` to raise `ParseError` immediately on any spec violation, rather than silently correcting it.

**Sanitizer filter** — `filters.sanitizer.Filter` keeps only elements and attributes on an explicit allow-list. It can be used standalone or enabled via `HTMLSerializer(sanitize=True)`.

```python
from markuptree.filters.sanitizer import Filter as Sanitizer
from markuptree.treewalkers.etree import TreeWalker
from markuptree.serializer import HTMLSerializer

# Custom allow-lists
safe_html = HTMLSerializer().render(
    Sanitizer(
        TreeWalker(doc),
        allowed_elements=frozenset(["p", "b", "i", "a"]),
        allowed_attrs=frozenset(["href", "class"]),
    )
)
```

## Encoding Detection

`HTMLInputStream` implements the WHATWG encoding sniffing algorithm. The detection priority is:

1. **Override encoding** — caller-supplied `override_encoding` parameter
2. **Transport encoding** — from HTTP `Content-Type` header (`transport_encoding` parameter)
3. **BOM detection** — UTF-8 BOM (`\xef\xbb\xbf`), UTF-32-BE/LE, UTF-16-BE/LE
4. **`<meta charset>` sniffing** — scans the first 1024 bytes for `<meta charset="...">` or `<meta http-equiv="Content-Type" content="...charset=...">`
5. **Same-origin parent encoding** — `same_origin_parent_encoding` parameter
6. **Likely encoding** — `likely_encoding` parameter
7. **chardet** — if the `chardet` package is installed and `use_chardet=True` (default)
8. **Fallback** — `windows-1252` (per the WHATWG spec default)

All encoding names are normalized through `codecs.lookup()`. Invalid or unrecognized names fall back to `windows-1252`.

```python
from markuptree.inputstream import HTMLInputStream

stream = HTMLInputStream(
    raw_bytes,
    transport_encoding="utf-8",  # from HTTP header
    use_chardet=True,            # try chardet if needed
)
print(stream.documentEncoding)  # resolved codec name
```

`HTMLInputStream` accepts `str`, `bytes`, or any file-like object with a `read()` method. String input is always treated as UTF-8. Bytes input goes through the full detection chain.

The stream also normalizes line endings (`\r\n` and `\r` both become `\n`) and replaces NULL bytes with U+FFFD, as required by the WHATWG spec.

## Token Format

All components communicate using plain dicts with a `"type"` key. This is the internal wire protocol between the tokenizer, tree builder, tree walker, and serializer.

| Token type | Keys |
|-----------|------|
| `Doctype` | `name`, `publicId`, `systemId` |
| `StartTag` | `name`, `namespace`, `data` (OrderedDict of attrs), `selfClosing` |
| `EndTag` | `name`, `namespace` |
| `EmptyTag` | `name`, `namespace`, `data` |
| `Characters` | `data` |
| `SpaceCharacters` | `data` |
| `Comment` | `data` |
| `Entity` | `name` |
| `ParseError` | `data` (error message) |
| `SerializeError` | `data` (error message) |

## Constants

`markuptree.constants` exposes the full set of HTML5 constants:

```python
from markuptree.constants import (
    tokenTypes,         # {"Doctype": 0, "Characters": 1, ...}
    namespaces,         # {"html": "http://www.w3.org/1999/xhtml", "svg": ..., "mathml": ...}
    voidElements,       # frozenset of void element names
    cdataElements,      # frozenset of CDATA elements
    rcdataElements,     # frozenset of RCDATA elements
    booleanAttributes,  # dict[element_name, frozenset[attr_name]]
    entities,           # named character entity → codepoint mappings
)
```

## Exceptions

```python
from markuptree import ParseError, SerializeError
from markuptree.exceptions import IncompleteParseError

# ParseError — raised in strict mode, or importable for isinstance checks
# SerializeError — raised on serialization errors
# IncompleteParseError — raised when parsing ends before the document is complete
# HTMLParseError — alias for ParseError (html5lib compatibility)
```

## Migration from html5lib

**The simplest migration is a one-line import change:**

```python
# Before
import html5lib

# After
import markuptree as html5lib
```

All html5lib public names are available on the `markuptree` module: `parse`, `parseFragment`, `getTreeBuilder`, `getTreeWalker`, `serialize`, `HTMLParser`, `ParseError`, `HTMLParseError`, `SerializeError`, and `HTMLSerializer`.

**Or use the compatibility shim directly:**

```python
from markuptree._compat import *
# Exports: parse, parseFragment, getTreeBuilder, getTreeWalker,
#          serialize, HTMLParser, HTMLSerializer,
#          ParseError, HTMLParseError, SerializeError
```

**Common html5lib patterns all work unchanged:**

```python
import markuptree as html5lib

# Parse to etree
doc = html5lib.parse("<p>hello</p>", treebuilder="etree")

# Parse to dom
doc = html5lib.parse("<p>hello</p>", treebuilder="dom")

# Parse fragment
frag = html5lib.parseFragment("<li>item</li>", container="ul")

# Serialize
walker = html5lib.getTreeWalker("etree")
serializer = html5lib.HTMLSerializer()
html = serializer.render(walker(doc))

# Detect encoding
parser = html5lib.HTMLParser()
doc = parser.parse(b"<p>hello</p>")
print(parser.documentEncoding)
```

**Key differences from html5lib:**

- Python 3.9+ only (no Python 2 support, no `six` dependency)
- `webencodings` is not used; encoding lookup goes through `codecs` directly
- The sanitizer filter is not deprecated and has updated safe defaults
- `HTMLParser(strict=True)` raises `ParseError` instead of silently recovering
- `escape_lt_in_attrs` is the attribute name (html5lib used `escape_lt_in_attribs` in some versions — both spellings are accepted)

## License

MIT
