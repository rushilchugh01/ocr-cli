from __future__ import annotations

import argparse
from typing import Any

from rapidocr import RapidOCR

from rapidocr_cli.engine import run_ocr_for_source
from rapidocr_cli.inputs import is_url
from rapidocr_cli.output import (
    build_pdf_page_record,
    build_pdf_record,
    choose_pdf_visualization_path,
    serialize_word_results,
)
from rapidocr_cli.pdf_quality import compute_pdf_layout_metrics, score_native_text_quality
from rapidocr_cli.types import InputItem, PDFPageDecision


def load_pdf_module(error_type: type[Exception]) -> Any:
    try:
        import fitz
    except ImportError as exc:
        raise error_type("PDF support requires PyMuPDF. Install the `pymupdf` package.") from exc
    return fitz


def is_pdf_runtime_ready(error_type: type[Exception]) -> bool:
    try:
        load_pdf_module(error_type)
    except Exception:
        return False
    return True


def parse_page_spec(page_spec: str | None, page_count: int, error_type: type[Exception]) -> list[int]:
    if not page_spec:
        return list(range(1, page_count + 1))

    selected: set[int] = set()
    for raw_part in page_spec.split(","):
        part = raw_part.strip()
        if not part:
            continue
        if "-" in part:
            start_text, end_text = part.split("-", 1)
            try:
                start = int(start_text)
                end = int(end_text)
            except ValueError as exc:
                raise error_type(f"Invalid page range: {part}") from exc
            if start > end:
                raise error_type(f"Invalid page range: {part}")
            pages = range(start, end + 1)
        else:
            try:
                pages = [int(part)]
            except ValueError as exc:
                raise error_type(f"Invalid page number: {part}") from exc

        for page in pages:
            if page < 1:
                raise error_type(f"Invalid page number: {page}")
            if page > page_count:
                raise error_type(f"Requested page {page} exceeds document page count {page_count}")
            selected.add(page)

    if not selected:
        raise error_type("No pages selected")
    return sorted(selected)


def rasterize_pdf_page(page: Any, dpi: int, error_type: type[Exception]) -> bytes:
    fitz = load_pdf_module(error_type)
    scale = max(float(dpi), 72.0) / 72.0
    pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
    return pixmap.tobytes("png")


def process_pdf_input(
    item: InputItem,
    engine: RapidOCR,
    args: argparse.Namespace,
    multiple_inputs: bool,
    error_type: type[Exception],
) -> dict[str, Any]:
    if is_url(item.source):
        raise error_type("PDF URLs are not supported yet. Download the PDF locally and try again.")

    fitz = load_pdf_module(error_type)
    try:
        document = fitz.open(item.source)
    except Exception as exc:
        raise error_type(f"Failed to open PDF: {item.display_name}: {exc}") from exc

    try:
        selected_pages = parse_page_spec(args.pages, document.page_count, error_type)
        page_records: list[PDFPageDecision] = []
        for page_number in selected_pages:
            page = document.load_page(page_number - 1)
            layout_metrics = compute_pdf_layout_metrics(page)
            native_text = ""
            if args.pdf_mode != "ocr":
                try:
                    native_text = page.get_text("text")
                except Exception:
                    native_text = ""

            quality = score_native_text_quality(native_text, layout_metrics)
            if args.pdf_mode == "text":
                page_records.append(
                    build_pdf_page_record(
                        item=item,
                        page_number=page_number,
                        quality=quality,
                        method_used="native_text",
                        text=quality["normalized_text"],
                        markdown=quality["normalized_text"],
                        lines=[],
                        elapsed_seconds=0.0,
                        visualization_path=None,
                        fallback_reason=None,
                    )
                )
                continue

            should_use_native = args.pdf_mode == "auto" and quality["accepted"]
            if should_use_native:
                page_records.append(
                    build_pdf_page_record(
                        item=item,
                        page_number=page_number,
                        quality=quality,
                        method_used="native_text",
                        text=quality["normalized_text"],
                        markdown=quality["normalized_text"],
                        lines=[],
                        elapsed_seconds=0.0,
                        visualization_path=None,
                        fallback_reason=None,
                    )
                )
                continue

            raster_bytes = rasterize_pdf_page(page, args.pdf_dpi, error_type)
            result = run_ocr_for_source(engine, raster_bytes, args)
            visualization_path = choose_pdf_visualization_path(args.save_vis, item, multiple_inputs, page_number)
            if visualization_path is not None:
                result.vis(str(visualization_path))

            lines = result.to_json() or []
            text = "\n".join(line["txt"] for line in lines)
            fallback_reason = "forced_ocr" if args.pdf_mode == "ocr" else "garbled_or_missing_native_text"
            word_results = serialize_word_results(result.word_results) if result.word_results is not None else None
            page_records.append(
                build_pdf_page_record(
                    item=item,
                    page_number=page_number,
                    quality=quality,
                    method_used="ocr",
                    text=text,
                    markdown=result.to_markdown(),
                    lines=lines,
                    elapsed_seconds=float(result.elapse),
                    visualization_path=visualization_path,
                    fallback_reason=fallback_reason,
                    word_results=word_results,
                )
            )
        return build_pdf_record(item, page_records)
    finally:
        document.close()
