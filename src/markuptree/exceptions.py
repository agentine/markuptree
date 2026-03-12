"""Exception classes for markuptree."""


class ParseError(Exception):
    """Raised in strict mode when a parse error is encountered."""
    pass


class SerializeError(Exception):
    """Raised when a serialization error occurs."""
    pass


class IncompleteParseError(ParseError):
    """Raised when parsing ends before the document is complete."""
    pass


# Aliases for html5lib compatibility
HTMLParseError = ParseError
