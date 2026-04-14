from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class InputItem:
    source: str
    display_name: str
    safe_stem: str


@dataclass(frozen=True)
class PDFPageDecision:
    page_number: int
    method_used: str
    text: str
    markdown: str
    lines: list[dict[str, Any]]
    elapsed_seconds: float
    status: str
    native_text_found: bool
    native_text_accepted: bool
    native_text_score: float
    decision: str
    fallback_reason: str | None
    quality_metrics: dict[str, Any]
    visualization_path: str | None
    word_results: list[list[dict[str, Any]]] | None = None
