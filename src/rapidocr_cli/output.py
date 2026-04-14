from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Sequence

from rapidocr_cli.types import InputItem, PDFPageDecision


def to_float_list(points: Any) -> list[list[float]]:
    return [[float(x), float(y)] for x, y in points]


def is_word_result_item(item: Any) -> bool:
    return isinstance(item, (list, tuple)) and len(item) == 3


def serialize_word_results(word_results: Any) -> list[list[dict[str, Any]]]:
    serialized: list[list[dict[str, Any]]] = []
    for line in word_results or ():
        line_items: list[dict[str, Any]] = []
        for item in line:
            if not is_word_result_item(item):
                continue
            text, score, box = item
            line_items.append({"txt": str(text), "score": float(score), "box": to_float_list(box)})
        serialized.append(line_items)
    return serialized


def choose_visualization_path(target: str | None, item: InputItem, multiple_inputs: bool) -> Path | None:
    if not target:
        return None

    candidate = Path(target)
    if multiple_inputs:
        candidate.mkdir(parents=True, exist_ok=True)
        return candidate / f"{item.safe_stem}.vis.png"

    if candidate.exists() and candidate.is_dir():
        return candidate / f"{item.safe_stem}.vis.png"

    if candidate.suffix:
        candidate.parent.mkdir(parents=True, exist_ok=True)
        return candidate

    candidate.mkdir(parents=True, exist_ok=True)
    return candidate / f"{item.safe_stem}.vis.png"


def choose_pdf_visualization_path(
    target: str | None,
    item: InputItem,
    multiple_inputs: bool,
    page_number: int,
) -> Path | None:
    path = choose_visualization_path(target, item, multiple_inputs)
    if path is None:
        return None
    if multiple_inputs or path.is_dir():
        return path / f"{item.safe_stem}.page-{page_number}.vis.png"
    if path.suffix:
        return path.with_name(f"{path.stem}.page-{page_number}{path.suffix}")
    return path / f"{item.safe_stem}.page-{page_number}.vis.png"


def build_record(item: InputItem, result: Any, visualization_path: Path | None) -> dict[str, Any]:
    lines = result.to_json() or []
    text = "\n".join(line["txt"] for line in lines)
    record: dict[str, Any] = {
        "input": item.display_name,
        "input_type": "image",
        "status": "ok" if lines else "no_text_detected",
        "method_used": "ocr",
        "text": text,
        "markdown": result.to_markdown(),
        "lines": lines,
        "elapsed_seconds": float(result.elapse),
        "visualization_path": str(visualization_path.resolve()) if visualization_path else None,
    }
    if result.word_results is not None:
        record["word_results"] = serialize_word_results(result.word_results)
    return record


def build_pdf_page_record(
    item: InputItem,
    page_number: int,
    quality: dict[str, Any],
    method_used: str,
    text: str,
    markdown: str,
    lines: list[dict[str, Any]],
    elapsed_seconds: float,
    visualization_path: Path | None,
    fallback_reason: str | None,
    word_results: list[list[dict[str, Any]]] | None = None,
) -> PDFPageDecision:
    status = "ok" if text.strip() or lines else "no_text_detected"
    return PDFPageDecision(
        page_number=page_number,
        method_used=method_used,
        text=text,
        markdown=markdown,
        lines=lines,
        elapsed_seconds=elapsed_seconds,
        status=status,
        native_text_found=bool(quality["normalized_text"]),
        native_text_accepted=bool(quality["accepted"]),
        native_text_score=float(quality["score"]),
        decision=quality["decision"],
        fallback_reason=fallback_reason,
        quality_metrics=quality["metrics"],
        visualization_path=str(visualization_path.resolve()) if visualization_path else None,
        word_results=word_results,
    )


def render_pdf_text(page_records: Sequence[PDFPageDecision]) -> str:
    chunks = []
    for page in page_records:
        body = page.text.strip()
        if body:
            chunks.append(f"--- Page {page.page_number} ---\n{body}")
    return "\n\n".join(chunks).strip()


def render_pdf_markdown(page_records: Sequence[PDFPageDecision]) -> str:
    chunks = []
    for page in page_records:
        body = page.markdown.strip() or page.text.strip()
        if body:
            chunks.append(f"## Page {page.page_number}\n\n{body}")
    return "\n\n".join(chunks).strip()


def build_pdf_record(item: InputItem, page_records: Sequence[PDFPageDecision]) -> dict[str, Any]:
    pages: list[dict[str, Any]] = []
    total_elapsed = 0.0
    no_text_pages = 0
    for page in page_records:
        payload: dict[str, Any] = {
            "page_number": page.page_number,
            "status": page.status,
            "method_used": page.method_used,
            "text": page.text,
            "markdown": page.markdown,
            "lines": page.lines,
            "elapsed_seconds": page.elapsed_seconds,
            "native_text_found": page.native_text_found,
            "native_text_accepted": page.native_text_accepted,
            "native_text_score": page.native_text_score,
            "decision": page.decision,
            "fallback_reason": page.fallback_reason,
            "quality_metrics": page.quality_metrics,
            "visualization_path": page.visualization_path,
        }
        if page.word_results is not None:
            payload["word_results"] = page.word_results
        pages.append(payload)
        total_elapsed += page.elapsed_seconds
        if page.status == "no_text_detected":
            no_text_pages += 1

    return {
        "input": item.display_name,
        "input_type": "pdf",
        "page_count": len(page_records),
        "status": "no_text_detected" if page_records and no_text_pages == len(page_records) else "ok",
        "text": render_pdf_text(page_records),
        "markdown": render_pdf_markdown(page_records),
        "lines": [],
        "elapsed_seconds": total_elapsed,
        "visualization_path": None,
        "pages": pages,
    }


def render_output(records: list[dict[str, Any]], output_format: str) -> str:
    if output_format == "json":
        return json.dumps(records, ensure_ascii=False, indent=2)

    if output_format == "markdown":
        if len(records) == 1:
            return records[0]["markdown"]
        chunks = [f"## {record['input']}\n\n{record['markdown']}".rstrip() for record in records]
        return "\n\n".join(chunks).strip()

    if len(records) == 1:
        return records[0]["text"]

    chunks = [f">>> {record['input']}\n{record['text']}".rstrip() for record in records]
    return "\n\n".join(chunks).strip()


def write_output(content: str, destination: str | None) -> None:
    if destination:
        path = Path(destination)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return

    if not sys.stdout.isatty() and hasattr(sys.stdout, "buffer"):
        sys.stdout.buffer.write(content.encode("utf-8"))
        sys.stdout.buffer.write(b"\n")
        return

    print(content)
