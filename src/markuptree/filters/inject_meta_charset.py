"""Filter that injects or replaces a <meta charset> tag."""

from __future__ import annotations

from typing import Any, Dict, Iterator, Optional

from markuptree.filters.base import Filter as BaseFilter


class Filter(BaseFilter):
    """Ensure the document has a ``<meta charset="...">`` tag.

    If a ``<meta charset>`` or ``<meta http-equiv="Content-Type">`` is
    found, its charset is replaced.  Otherwise a new ``<meta charset>``
    is injected after ``<head>``.
    """

    def __init__(self, source: Any, encoding: str = "utf-8") -> None:
        super().__init__(source)
        self.encoding = encoding

    def __iter__(self) -> Iterator[Dict[str, Any]]:
        state = "pre_head"
        meta_found = False

        for token in self.source:
            ttype = token["type"]

            if state == "pre_head":
                if ttype == "StartTag" and token["name"] == "head":
                    yield token
                    state = "in_head"
                    continue
                yield token

            elif state == "in_head":
                if ttype in ("StartTag", "EmptyTag") and token["name"] == "meta":
                    attrs = token.get("data", {})
                    if "charset" in attrs:
                        token = dict(token)
                        token["data"] = dict(attrs)
                        token["data"]["charset"] = self.encoding
                        meta_found = True
                    elif attrs.get("http-equiv", "").lower() == "content-type":
                        token = dict(token)
                        token["data"] = dict(attrs)
                        token["data"]["content"] = f"text/html; charset={self.encoding}"
                        meta_found = True
                    yield token
                elif ttype == "EndTag" and token["name"] == "head":
                    if not meta_found:
                        yield {
                            "type": "EmptyTag",
                            "namespace": token.get("namespace"),
                            "name": "meta",
                            "data": {"charset": self.encoding},
                        }
                    yield token
                    state = "post_head"
                else:
                    yield token

            else:
                yield token
