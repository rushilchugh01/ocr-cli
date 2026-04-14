from __future__ import annotations

import re
import unicodedata
from typing import Any, Sequence


def normalize_text(value: str) -> str:
    if not value:
        return ""
    text = value.replace("\x00", "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.strip() for line in text.split("\n")]
    text = "\n".join(line for line in lines if line)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def ratio(numerator: int | float, denominator: int | float) -> float:
    if not denominator:
        return 0.0
    return float(numerator) / float(denominator)


def bbox_area(bbox: Sequence[float]) -> float:
    if len(bbox) != 4:
        return 0.0
    x0, y0, x1, y1 = bbox
    return max(0.0, float(x1) - float(x0)) * max(0.0, float(y1) - float(y0))


def compute_pdf_layout_metrics(page: Any) -> dict[str, Any]:
    page_rect = getattr(page, "rect", None)
    page_area = 1.0
    if page_rect is not None:
        page_area = max(1.0, float(getattr(page_rect, "width", 0.0)) * float(getattr(page_rect, "height", 0.0)))

    block_data = {}
    try:
        block_data = page.get_text("dict") or {}
    except Exception:
        block_data = {}

    text_area = 0.0
    image_area = 0.0
    for block in block_data.get("blocks", []):
        area = bbox_area(block.get("bbox", []))
        if block.get("type") == 1:
            image_area += area
        else:
            text_area += area

    return {
        "text_coverage": min(1.0, ratio(text_area, page_area)),
        "image_coverage": min(1.0, ratio(image_area, page_area)),
    }


def score_native_text_quality(native_text: str, layout_metrics: dict[str, Any]) -> dict[str, Any]:
    normalized_text = normalize_text(native_text)
    char_count = len(normalized_text)
    printable_count = sum(ch.isprintable() or ch in "\n\t" for ch in normalized_text)
    replacement_count = normalized_text.count("\ufffd")
    control_count = sum(unicodedata.category(ch) == "Cc" for ch in normalized_text if ch not in "\n\t")
    private_use_count = sum(unicodedata.category(ch) == "Co" for ch in normalized_text)
    alnum_count = sum(ch.isalnum() for ch in normalized_text)
    whitespace_count = sum(ch.isspace() for ch in normalized_text)
    punctuation_count = sum(unicodedata.category(ch).startswith("P") for ch in normalized_text)
    weird_symbol_count = max(0, char_count - alnum_count - whitespace_count - punctuation_count)

    printable_ratio = ratio(printable_count, char_count)
    replacement_ratio = ratio(replacement_count, char_count)
    weird_symbol_ratio = ratio(weird_symbol_count + control_count + private_use_count, char_count)
    image_coverage = float(layout_metrics.get("image_coverage", 0.0))
    text_coverage = float(layout_metrics.get("text_coverage", 0.0))

    score = 0.0
    if char_count >= 12:
        score += 0.36
    elif char_count >= 6:
        score += 0.2

    score += 0.25 * printable_ratio
    score += 0.2 * min(text_coverage * 2.0, 1.0)
    score -= 0.55 * replacement_ratio
    score -= 0.45 * weird_symbol_ratio
    score -= 0.2 * image_coverage
    score = max(0.0, min(1.0, score))

    accepted = bool(normalized_text) and score >= 0.55
    if accepted:
        decision = "use_native_text"
    elif normalized_text:
        decision = "borderline_fallback_to_ocr" if score >= 0.35 else "fallback_to_ocr"
    else:
        decision = "fallback_to_ocr"

    return {
        "normalized_text": normalized_text,
        "score": score,
        "accepted": accepted,
        "decision": decision,
        "metrics": {
            "char_count": char_count,
            "printable_ratio": printable_ratio,
            "replacement_ratio": replacement_ratio,
            "weird_symbol_ratio": weird_symbol_ratio,
            "text_coverage": text_coverage,
            "image_coverage": image_coverage,
        },
    }
