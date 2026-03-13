# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-03-13

Initial release of **markuptree** — a modern, zero-dependency drop-in replacement for [html5lib](https://github.com/html5lib/html5lib-python) implementing the WHATWG HTML5 parsing algorithm.

### Added

- **`InputStream`** (`input.py`) — encoding detection (BOM, meta charset, HTTP header), character normalization (invalid Unicode surrogate replacement, control character handling), chunked streaming.
- **HTML5 tokenizer** (`tokenizer.py`) — WHATWG tokenizer state machine: 80+ states covering all HTML5 token types (DOCTYPE, start/end tags, comments, character data, CDATA sections, RCDATA, RAWTEXT). Correct handling of named and numeric character references.
- **Tree construction algorithm** (`treebuilder/base.py`) — full HTML5 tree construction: all 18 insertion modes, adoption agency algorithm for formatting element reconstruction, foster parenting, `<template>` content, `<html>`/`<head>`/`<body>` implicit insertion, `<table>`/`<select>` special handling.
- **`SimpleTreeBuilder`** (`treebuilder/base.py`) — lightweight internal tree representation (Element, Comment, Doctype, Document nodes).
- **`etree` backend** (`treebuilder/etree.py`) — builds `xml.etree.ElementTree` trees directly.
- **`dom` backend** (`treebuilder/dom.py`) — builds `xml.dom.minidom` Document objects.
- **HTML serializer** (`serializer.py`) — `HTMLSerializer` with void element detection, optional quote minimization, attribute encoding, `inject_meta_charset`, `omit_optional_tags`, `alphabetical_attributes`. Produces spec-compliant HTML output.
- **Tree walkers** (`treewalkers/`) — `getTreeWalker` factory; base `TreeWalker`, `etree` walker.
- **Sanitizer** (`filters/sanitizer.py`) — allowlist-based HTML sanitizer via `SanitizerFilter`; configurable `allowed_elements`, `allowed_attributes`, `allowed_protocols`, `allowed_css_properties`.
- **`HTMLParser`** (`html5parser.py`) — top-level `parse(doc)`, `parseFragment(doc)`, `parseError` list; tree builder selection via `treebuilder` kwarg.
- **Compat shim** (`__init__.py`) — `markuptree.parse`, `markuptree.parseFragment`, `markuptree.serialize`, `markuptree.getTreeBuilder`, `markuptree.getTreeWalker` mirror the html5lib public API for drop-in replacement.
- **Optional backends** — `pip install markuptree[lxml]` for lxml tree builder; `pip install markuptree[chardet]` for chardet encoding detection.
- **Zero required dependencies** — stdlib only; optional extras for lxml and chardet.
- **227 tests** passing.

### Security

- **RCDATA/RAWTEXT state switching** — tree builder correctly switches tokenizer to `rcdata`/`rawtext` state for `<script>`, `<style>`, `<textarea>`, `<title>` elements, preventing content in those elements from being parsed as tags (XSS vector).
- **Comment `-->` breakout prevented** — `--` sequences in comment content replaced with `- -` during serialization.
- **Script/style CDATA escaping** — `</script>` and `</style>` sequences in inline script/style blocks are escaped to prevent early tag close injection.
- **Strict mode** (`strict=True`) — raises `ParseError` on any parse error rather than silently recovering; enforcement uses correct token-type comparison.

### Fixed

- BOM detection: 4-byte UTF-32 checks precede 2-byte UTF-16 checks to prevent UTF-32-LE misdetection as UTF-16-LE.
- `resolve_entities` filter: correctly threads through the serialization pipeline.
- RCDATA tokenizer state: tree builder now stores and switches tokenizer state reference.
- Strict mode: parse error comparison uses `tokenTypes["ParseError"]` integer constant (not string).
