"""Normalize untrusted text before it is persisted or sent to an AI model."""

from __future__ import annotations

import html
import re


def sanitize_untrusted_text(raw_text: str, *, max_chars: int | None = None) -> str:
    value = html.unescape(str(raw_text or ""))
    value = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", value)
    value = re.sub(r"(?is)<!--.*?-->", " ", value)
    value = re.sub(r"(?s)<[^>]+>", "\n", value)
    value = value.replace("\x00", " ")
    value = "\n".join(" ".join(line.split()) for line in value.splitlines() if line.strip())
    if max_chars is not None:
        value = value[:max_chars]
    return value
