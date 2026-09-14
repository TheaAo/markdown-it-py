from __future__ import annotations

import re


EMPTY_BLOCKQUOTE = re.compile(r"<blockquote>\n</blockquote>")


def canonical_commonmark_html(html: str) -> str:
    """Normalize the one documented renderer/spec formatting difference."""
    return EMPTY_BLOCKQUOTE.sub("<blockquote></blockquote>", html).replace("\r\n", "\n")
