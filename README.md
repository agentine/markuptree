# markuptree

A modern, zero-dependency drop-in replacement for [html5lib](https://github.com/html5lib/html5lib-python).

## Installation

```bash
pip install markuptree
```

## Quickstart

```python
import markuptree

# Parse an HTML document
doc = markuptree.parse("<html><body><p>Hello <b>world</b></p></body></html>")

# Parse a fragment
fragments = markuptree.parseFragment("<p>Hello</p><p>World</p>")

# Serialize a tree back to HTML
html = markuptree.serialize(doc, tree="etree")

# Use the HTMLParser class directly
parser = markuptree.HTMLParser(tree="etree")
doc = parser.parse("<p>Hello</p>")
print(parser.errors)           # list of parse errors
print(parser.documentEncoding) # detected encoding
```

## Tree Builders

Two built-in backends for constructing parse trees:

| Backend | Description |
|---------|-------------|
| `"etree"` | Uses `xml.etree.ElementTree` (default) |
| `"dom"` | Uses `xml.dom.minidom` |

```python
# Get a tree builder class
TB = markuptree.getTreeBuilder("etree")
```

## Tree Walkers

Walk a parsed tree and yield serializer tokens:

```python
Walker = markuptree.getTreeWalker("etree")
walker = Walker(doc)
for token in walker:
    print(token)
```

## Serializer

```python
from markuptree.serializer import HTMLSerializer

Walker = markuptree.getTreeWalker("etree")
s = HTMLSerializer(
    omit_optional_tags=True,
    quote_attr_values="always",
    minimize_boolean_attributes=True,
    alphabetical_attributes=True,
)
html = s.render(Walker(doc))
```

### Serializer Options

| Option | Default | Description |
|--------|---------|-------------|
| `quote_attr_values` | `"legacy"` | `"legacy"` (quote when needed) or `"always"` |
| `quote_char` | `'"'` | Quote character for attributes |
| `use_best_quote_char` | `True` | Pick `'` or `"` to minimize escaping |
| `omit_optional_tags` | `True` | Omit optional start/end tags |
| `minimize_boolean_attributes` | `True` | `disabled` instead of `disabled="disabled"` |
| `use_trailing_solidus` | `False` | `<br />` instead of `<br>` |
| `space_before_trailing_solidus` | `True` | Space before `/>` |
| `escape_lt_in_attrs` | `False` | Escape `<` in attribute values |
| `resolve_entities` | `True` | Resolve character entities |
| `alphabetical_attributes` | `False` | Sort attributes alphabetically |
| `inject_meta_charset` | `True` | Inject `<meta charset>` |
| `strip_whitespace` | `False` | Collapse whitespace |
| `sanitize` | `False` | Strip unsafe elements/attributes |

## Filters

Token stream filters that sit between a tree walker and the serializer:

```python
from markuptree.treewalkers.etree import TreeWalker
from markuptree.filters.sanitizer import Filter as SanitizerFilter
from markuptree.serializer import HTMLSerializer

walker = TreeWalker(doc)
safe = SanitizerFilter(walker)
html = HTMLSerializer().render(safe)
```

| Filter | Description |
|--------|-------------|
| `filters.base` | Passthrough base class |
| `filters.alphabeticalattributes` | Sort attributes A-Z |
| `filters.inject_meta_charset` | Inject/replace `<meta charset>` |
| `filters.whitespace` | Collapse whitespace (preserves `<pre>`) |
| `filters.optionaltags` | Omit optional end tags |
| `filters.sanitizer` | Strip unsafe elements, attributes, URI schemes |
| `filters.lint` | Emit warnings for void/non-void tag misuse |

## Migration from html5lib

```python
# Change this:
import html5lib

# To this:
import markuptree as html5lib
```

Or use the compatibility shim:

```python
from markuptree._compat import *
```

## License

MIT
