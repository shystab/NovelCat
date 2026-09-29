"""Lightweight token estimation for context budgeting.

Exact token counts depend on the model's tokenizer and are not available
before an API call. We use a conservative CJK-aware heuristic and can
calibrate against provider `usage` values later.
"""

from __future__ import annotations

import re
from typing import Any


_CJK_RE = re.compile(r"[\u3000-\u303f\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


def estimate_tokens(text: str | None) -> int:
    """Estimate tokens: CJK chars ~1 token, other text ~4 chars/token."""
    if not text:
        return 0
    cjk_chars = len(_CJK_RE.findall(text))
    other_chars = max(0, len(text) - cjk_chars)
    return cjk_chars + (other_chars + 3) // 4


def estimate_messages_tokens(messages: list[dict[str, Any]] | None) -> int:
    """Estimate the token cost of a message list, including small role overhead."""
    total = 0
    for message in messages or []:
        content = message.get("content")
        if isinstance(content, str) and content:
            total += estimate_tokens(content) + 4
        elif isinstance(content, list):
            total += estimate_tokens(str(content)) + 4
    return total
