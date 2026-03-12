"""markuptree — a modern, zero-dependency drop-in replacement for html5lib."""

from __future__ import annotations

from typing import Any, Optional

from markuptree.exceptions import ParseError, SerializeError  # noqa: F401

__version__ = "0.1.0"


def parse(
    doc: Any,
    treebuilder: str = "etree",
    namespaceHTMLElements: bool = True,
    **kwargs: Any,
) -> Any:
    """Parse an HTML document and return a tree."""
    p = HTMLParser(
        tree=treebuilder, namespaceHTMLElements=namespaceHTMLElements
    )
    return p.parse(doc, **kwargs)


def parseFragment(
    doc: Any,
    container: str = "div",
    treebuilder: str = "etree",
    namespaceHTMLElements: bool = True,
    **kwargs: Any,
) -> Any:
    """Parse an HTML fragment and return a tree."""
    p = HTMLParser(
        tree=treebuilder, namespaceHTMLElements=namespaceHTMLElements
    )
    return p.parseFragment(doc, container=container, **kwargs)


def getTreeBuilder(name: str, implementation: Any = None, **kwargs: Any) -> Any:
    """Get a TreeBuilder class by name."""
    from markuptree.treebuilders import getTreeBuilder as _get

    return _get(name, implementation, **kwargs)


def getTreeWalker(name: str, implementation: Any = None, **kwargs: Any) -> Any:
    """Get a TreeWalker class by name."""
    from markuptree.treewalkers import getTreeWalker as _get

    return _get(name, implementation, **kwargs)


def serialize(
    input: Any,
    tree: str = "etree",
    encoding: Optional[str] = None,
    **serializer_opts: Any,
) -> str:
    """Serialize a tree to an HTML string."""
    from markuptree.serializer import serialize as _serialize

    return _serialize(input, tree=tree, encoding=encoding, **serializer_opts)


class HTMLParser:
    """HTML parser that wraps the tokenizer and tree builder."""

    def __init__(
        self,
        tree: Any = None,
        strict: bool = False,
        namespaceHTMLElements: bool = True,
        debug: bool = False,
    ) -> None:
        self.strict = strict
        self.namespaceHTMLElements = namespaceHTMLElements
        self.debug = debug
        self._tree = tree or "etree"
        self._documentEncoding: Optional[str] = None
        self._errors: list[tuple[Any, ...]] = []

    def _get_tree_builder(self) -> Any:
        from markuptree.treebuilders import getTreeBuilder
        return getTreeBuilder(self._tree)

    def parse(self, stream: Any, *args: Any, **kwargs: Any) -> Any:
        """Parse a full HTML document and return the tree."""
        from markuptree.inputstream import HTMLInputStream
        from markuptree.tokenizer import HTMLTokenizer

        TB = self._get_tree_builder()
        tb = TB(namespaceHTMLElements=self.namespaceHTMLElements)

        input_stream = HTMLInputStream(stream)
        self._documentEncoding = input_stream.documentEncoding

        tokenizer = HTMLTokenizer(input_stream)
        for token in tokenizer:
            ttype = token.get("type")
            if ttype == "ParseError":
                self._errors.append((token.get("data", ""),))
            tb.processToken(token)

        return tb.getDocument()

    def parseFragment(
        self,
        stream: Any,
        *args: Any,
        container: str = "div",
        scripting: bool = False,
        **kwargs: Any,
    ) -> Any:
        """Parse an HTML fragment and return a list of nodes."""
        from markuptree.inputstream import HTMLInputStream
        from markuptree.tokenizer import HTMLTokenizer

        TB = self._get_tree_builder()
        tb = TB(namespaceHTMLElements=self.namespaceHTMLElements)

        input_stream = HTMLInputStream(stream)
        self._documentEncoding = input_stream.documentEncoding

        tokenizer = HTMLTokenizer(input_stream)
        for token in tokenizer:
            ttype = token.get("type")
            if ttype == "ParseError":
                self._errors.append((token.get("data", ""),))
            tb.processToken(token)

        return tb.getFragment()

    @property
    def documentEncoding(self) -> Optional[str]:
        """Return the encoding detected during parsing."""
        return self._documentEncoding

    @property
    def errors(self) -> list[tuple[Any, ...]]:
        """Return the list of parse errors encountered."""
        return self._errors
