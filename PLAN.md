# markuptree — Drop-in Replacement for html5lib

## Overview

**Target:** [html5lib](https://github.com/html5lib/html5lib-python) — the only pure-Python HTML5-compliant parser
**Package:** `markuptree` on PyPI
**License:** MIT
**Python:** 3.9+
**Dependencies:** Zero required (optional: lxml, chardet)

## Why Replace html5lib

- Last release: June 2020 (6 years ago)
- 30M monthly PyPI downloads
- Effectively abandoned — no active maintainers
- Caused the deprecation of bleach (Mozilla HTML sanitizer)
- Depends on `six` (Python 2 compat) and `webencodings` (unnecessary with modern stdlib)
- 95 open issues with no triage
- Critical dependency for pip, bleach, and hundreds of other packages

## Architecture

markuptree implements the WHATWG HTML5 parsing algorithm as a modular pipeline:

```
Input → InputStream → Tokenizer → TreeBuilder → Tree
                                                  ↓
                                            TreeWalker → Filter(s) → Serializer → Output
```

Components are connected via a token-based wire protocol (dict objects with `type` keys).

### Core Components

1. **InputStream** — handles encoding detection (BOM → meta → chardet → fallback) and character normalization
2. **Tokenizer** — state machine implementing the HTML5 tokenization spec, yields token dicts
3. **TreeBuilder** — constructs a tree from tokens using the HTML5 tree construction algorithm
4. **TreeWalker** — traverses a tree and yields tokens for serialization
5. **Serializer** — converts token stream back to HTML string/bytes
6. **Filters** — transform token streams between walker and serializer

## Public API Surface

### Module-Level Functions

```python
parse(doc, treebuilder="etree", namespaceHTMLElements=True, **kwargs)
parseFragment(doc, container="div", treebuilder="etree", namespaceHTMLElements=True, **kwargs)
getTreeBuilder(treeType, implementation=None, **kwargs)
getTreeWalker(treeType, implementation=None, **kwargs)
serialize(input, tree="etree", encoding=None, **serializer_opts)
```

### HTMLParser Class

```python
class HTMLParser:
    def __init__(self, tree=None, strict=False, namespaceHTMLElements=True, debug=False)
    def parse(self, stream, *args, **kwargs) -> tree
    def parseFragment(self, stream, *args, container="div", scripting=False, **kwargs) -> fragment
    @property
    def documentEncoding(self) -> Optional[str]
    @property
    def errors(self) -> List[tuple]
```

### TreeBuilder Backends

| Backend | Module | Default `implementation` |
|---------|--------|--------------------------|
| `"etree"` | `markuptree.treebuilders.etree` | `xml.etree.ElementTree` |
| `"dom"` | `markuptree.treebuilders.dom` | `xml.dom.minidom` |
| `"lxml"` | `markuptree.treebuilders.etree_lxml` | `lxml.etree` |

Base interface: `TreeBuilder` with `reset()`, `insertRoot()`, `insertDoctype()`, `insertComment()`, `createElement()`, `insertText()`, `getDocument()`, `getFragment()`, `generateImpliedEndTags()`, etc.

### TreeWalker Backends

| Backend | Module |
|---------|--------|
| `"etree"` | `markuptree.treewalkers.etree` |
| `"dom"` | `markuptree.treewalkers.dom` |
| `"lxml"` | `markuptree.treewalkers.etree_lxml` |
| `"genshi"` | `markuptree.treewalkers.genshi` |

Base interface: `TreeWalker.__iter__()` yielding token dicts, plus helper methods `startTag()`, `endTag()`, `text()`, `comment()`, `doctype()`, `emptyTag()`, `error()`.

### HTMLSerializer

```python
class HTMLSerializer:
    # 14 options with defaults
    quote_attr_values = "legacy"
    quote_char = '"'
    use_best_quote_char = True
    omit_optional_tags = True
    minimize_boolean_attributes = True
    use_trailing_solidus = False
    space_before_trailing_solidus = True
    escape_lt_in_attrs = False
    escape_rcdata = False
    resolve_entities = True
    alphabetical_attributes = False
    inject_meta_charset = True
    strip_whitespace = False
    sanitize = False

    def serialize(self, treewalker, encoding=None)  # generator
    def render(self, treewalker, encoding=None)      # returns string/bytes
```

### Filters

1. **`alphabeticalattributes.Filter(source)`** — sorts attributes alphabetically
2. **`inject_meta_charset.Filter(source, encoding)`** — injects/updates `<meta charset>`
3. **`lint.Filter(source, require_matching_tags=True)`** — validates token stream
4. **`optionaltags.Filter(source)`** — removes optional start/end tags
5. **`sanitizer.Filter(source, allowed_elements=..., ...)`** — strips unsafe content (with modern defaults, not deprecated)
6. **`whitespace.Filter(source)`** — collapses whitespace

### Tree Adapters

```python
markuptree.treeadapters.sax.to_sax(walker, handler)     # token stream → SAX events
markuptree.treeadapters.genshi.to_genshi(walker)         # token stream → Genshi events
```

### Token Format (Wire Protocol)

All tokens are dicts:
- `{"type": "Doctype", "name": str, "publicId": str, "systemId": str}`
- `{"type": "StartTag", "name": str, "namespace": str, "data": OrderedDict, "selfClosing": bool}`
- `{"type": "EndTag", "name": str, "namespace": str}`
- `{"type": "EmptyTag", "name": str, "namespace": str, "data": OrderedDict}`
- `{"type": "Characters", "data": str}`
- `{"type": "SpaceCharacters", "data": str}`
- `{"type": "Comment", "data": str}`
- `{"type": "Entity", "name": str}`
- `{"type": "ParseError", "data": str}`
- `{"type": "SerializeError", "data": str}`

### Constants Module

- `tokenTypes` — dict mapping type names to int IDs
- `namespaces` — HTML, MathML, SVG, XLink, XML, XMLNS namespace URIs
- `voidElements`, `cdataElements`, `rcdataElements` — element category frozensets
- `scopingElements`, `formattingElements`, `specialElements` — (namespace, name) frozenset tuples
- `booleanAttributes` — dict of element→attribute frozensets
- `entities` — ~2000+ named character entity mappings
- `E` — error code → message mapping

### Exceptions

- `ParseError(Exception)` — raised in strict mode on parse errors
- `SerializeError(Exception)` — raised on serialization errors

## Key Improvements Over html5lib

1. **Zero required dependencies** — drop `six` (Python 3.9+ only), replace `webencodings` with stdlib `codecs`
2. **Full type annotations** — complete type stubs for IDE support
3. **Modern sanitizer** — not deprecated, with safe defaults and CSP-aware filtering
4. **Performance** — optimize hot paths in tokenizer/tree construction with `__slots__`, avoid unnecessary copies
5. **Encoding detection** — use stdlib `codecs` for encoding lookup, optional `chardet` for auto-detection
6. **Better error messages** — structured error objects with line/column info
7. **InfosetFilter cleanup** — modernize XML name coercion without legacy workarounds

## Implementation Phases

### Phase 1: Tokenizer & InputStream (Core Engine)
- Encoding detection (BOM, meta, chardet, fallback chain)
- Character reference handling
- HTML5 tokenizer state machine (all states per WHATWG spec)
- Token dict wire format
- Constants module (entities, namespaces, element sets)

### Phase 2: Tree Construction & Builders
- Base TreeBuilder with full HTML5 tree construction algorithm
- etree backend (default, using xml.etree.ElementTree)
- dom backend (using xml.dom.minidom)
- lxml backend (optional, using lxml.etree)
- Scope management, active formatting elements, foster parenting

### Phase 3: Walkers, Serializer & Filters
- Base TreeWalker and NonRecursiveTreeWalker
- All 4 walker backends (etree, dom, lxml, genshi)
- HTMLSerializer with all 14 options
- All 6 filters
- Tree adapters (SAX, Genshi)

### Phase 4: Polish & Ship
- html5lib-tests integration (shared test suite with html5lib)
- Performance benchmarking against html5lib
- Migration guide (import markuptree as html5lib)
- PyPI package, CI/CD, documentation
- Compatibility shim module for seamless migration
