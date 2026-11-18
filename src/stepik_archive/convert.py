"""HTML to Markdown conversion and safe path helpers."""

from __future__ import annotations

import re

from markdownify import markdownify as md


def html_to_markdown(html: str | None) -> str:
    if not html:
        return ""
    text = md(html, heading_style="ATX", bullets="-")
    # Collapse excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


def safe_filename(name: str, max_length: int = 80) -> str:
    """Keep letters/digits/spaces/dashes/dots; collapse whitespace."""
    cleaned = re.sub(r"[^\w\s.\-]+", "", str(name), flags=re.UNICODE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = cleaned.replace(" ", "_")
    if not cleaned:
        cleaned = "untitled"
    return cleaned[:max_length].rstrip("._-")


def numbered_name(position: int, title: str, width: int = 2) -> str:
    return f"{str(position).zfill(width)}_{safe_filename(title)}"
