from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable, Sequence, TextIO

from rapidocr_cli.types import InputItem, PDFPageDecision

NO_VALID_TEXT_REASON = "no_valid_text_detected"
NO_VALID_TEXT_MESSAGE = "No valid text detected."


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


def build_content_status(text: str, lines: list[dict[str, Any]]) -> tuple[str, str | None, str | None]:
    if text.strip() or lines:
        return "ok", None, None
    return "no_text_detected", NO_VALID_TEXT_REASON, NO_VALID_TEXT_MESSAGE


def build_record(item: InputItem, result: Any, visualization_path: Path | None) -> dict[str, Any]:
    lines = result.to_json() or []
    text = "\n".join(line["txt"] for line in lines)
    status, reason, message = build_content_status(text, lines)
    record: dict[str, Any] = {
        "input": item.display_name,
        "input_type": "image",
        "status": status,
        "reason": reason,
        "message": message,
        "method_used": "ocr",
        "text": text,
        "markdown": result.to_markdown() if status == "ok" else "",
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
    status, reason, message = build_content_status(text, lines)
    return PDFPageDecision(
        page_number=page_number,
        method_used=method_used,
        text=text,
        markdown=markdown if status == "ok" else "",
        lines=lines,
        elapsed_seconds=elapsed_seconds,
        status=status,
        reason=reason,
        message=message,
        native_text_found=bool(quality["normalized_text"]),
        native_text_accepted=bool(quality["accepted"]),
        native_text_score=float(quality["score"]),
        decision=quality["decision"],
        fallback_reason=fallback_reason,
        quality_metrics=quality["metrics"],
        visualization_path=str(visualization_path.resolve()) if visualization_path else None,
        word_results=word_results,
    )


def build_pdf_page_payload(page: PDFPageDecision) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "page_number": page.page_number,
        "status": page.status,
        "reason": page.reason,
        "message": page.message,
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
    return payload


def render_pdf_text(page_records: Iterable[PDFPageDecision]) -> str:
    chunks = []
    for page in page_records:
        body = page.text.strip()
        if body:
            chunks.append(f"--- Page {page.page_number} ---\n{body}")
    return "\n\n".join(chunks).strip()


def render_pdf_markdown(page_records: Iterable[PDFPageDecision]) -> str:
    chunks = []
    for page in page_records:
        body = page.markdown.strip() or page.text.strip()
        if body:
            chunks.append(f"## Page {page.page_number}\n\n{body}")
    return "\n\n".join(chunks).strip()


def build_pdf_record(item: InputItem, page_records: Iterable[PDFPageDecision]) -> dict[str, Any]:
    pages: list[dict[str, Any]] = []
    page_count = 0
    total_elapsed = 0.0
    no_text_pages = 0
    text_chunks: list[str] = []
    markdown_chunks: list[str] = []
    for page in page_records:
        page_count += 1
        payload = build_pdf_page_payload(page)
        pages.append(payload)
        total_elapsed += page.elapsed_seconds
        if page.status == "no_text_detected":
            no_text_pages += 1
        text_body = page.text.strip()
        if text_body:
            text_chunks.append(f"--- Page {page.page_number} ---\n{text_body}")
        markdown_body = page.markdown.strip() or text_body
        if markdown_body:
            markdown_chunks.append(f"## Page {page.page_number}\n\n{markdown_body}")

    pages_with_text = page_count - no_text_pages
    status = "no_text_detected" if page_count and no_text_pages == page_count else "ok"
    reason = NO_VALID_TEXT_REASON if status == "no_text_detected" else None
    message = NO_VALID_TEXT_MESSAGE if status == "no_text_detected" else None

    return {
        "input": item.display_name,
        "input_type": "pdf",
        "page_count": page_count,
        "pages_with_text": pages_with_text,
        "no_text_pages": no_text_pages,
        "status": status,
        "reason": reason,
        "message": message,
        "text": "\n\n".join(text_chunks).strip(),
        "markdown": "\n\n".join(markdown_chunks).strip(),
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


def _copy_text_stream(source: TextIO, destination: TextIO, chunk_size: int = 16384) -> None:
    while True:
        chunk = source.read(chunk_size)
        if not chunk:
            break
        destination.write(chunk)


def _copy_output_path_to_stdout(path: Path) -> None:
    if not sys.stdout.isatty() and hasattr(sys.stdout, "buffer"):
        with path.open("rb") as handle:
            shutil.copyfileobj(handle, sys.stdout.buffer)
        sys.stdout.buffer.write(b"\n")
        return

    with path.open("r", encoding="utf-8") as handle:
        sys.stdout.write(handle.read())
    sys.stdout.write("\n")


def _write_json_string_from_file(target: TextIO, path: Path, chunk_size: int = 16384) -> None:
    escapes = {
        '"': '\\"',
        "\\": "\\\\",
        "\b": "\\b",
        "\f": "\\f",
        "\n": "\\n",
        "\r": "\\r",
        "\t": "\\t",
    }
    target.write('"')
    with path.open("r", encoding="utf-8") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            for char in chunk:
                escaped = escapes.get(char)
                if escaped is not None:
                    target.write(escaped)
                elif ord(char) < 0x20:
                    target.write(f"\\u{ord(char):04x}")
                else:
                    target.write(char)
    target.write('"')


def _write_indented_json_block(target: TextIO, value: str, indent: str) -> None:
    lines = value.splitlines()
    if not lines:
        target.write(f"{indent}{value}")
        return
    for index, line in enumerate(lines):
        if index:
            target.write("\n")
        target.write(indent)
        target.write(line)


class PDFRecordSpool:
    def __init__(self, root_dir: Path):
        self.root_dir = Path(tempfile.mkdtemp(prefix="pdf-spool-", dir=root_dir))
        self.pages_path = self.root_dir / "pages.jsonl"
        self.text_path = self.root_dir / "text.txt"
        self.markdown_path = self.root_dir / "markdown.md"
        self._pages_handle = self.pages_path.open("w", encoding="utf-8")
        self._text_handle = self.text_path.open("w", encoding="utf-8")
        self._markdown_handle = self.markdown_path.open("w", encoding="utf-8")
        self.page_count = 0
        self.total_elapsed = 0.0
        self.no_text_pages = 0
        self._first_text_chunk = True
        self._first_markdown_chunk = True
        self._closed = False

    def append_page(self, page: PDFPageDecision) -> None:
        self._pages_handle.write(json.dumps(build_pdf_page_payload(page), ensure_ascii=False))
        self._pages_handle.write("\n")
        self.page_count += 1
        self.total_elapsed += page.elapsed_seconds
        if page.status == "no_text_detected":
            self.no_text_pages += 1

        text_body = page.text.strip()
        if text_body:
            if not self._first_text_chunk:
                self._text_handle.write("\n\n")
            self._text_handle.write(f"--- Page {page.page_number} ---\n{text_body}")
            self._first_text_chunk = False

        markdown_body = page.markdown.strip() or text_body
        if markdown_body:
            if not self._first_markdown_chunk:
                self._markdown_handle.write("\n\n")
            self._markdown_handle.write(f"## Page {page.page_number}\n\n{markdown_body}")
            self._first_markdown_chunk = False

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for handle in (self._pages_handle, self._text_handle, self._markdown_handle):
            handle.flush()
            handle.close()

    def cleanup(self) -> None:
        shutil.rmtree(self.root_dir, ignore_errors=True)


class OutputSession:
    def __init__(self, output_format: str, destination: str | None, multiple_inputs: bool):
        self.output_format = output_format
        self.destination = destination
        self.multiple_inputs = multiple_inputs
        self._root_dir = Path(tempfile.mkdtemp(prefix="rapidocr-cli-"))
        self._output_path = self._root_dir / "output.tmp"
        self._handle = self._output_path.open("w", encoding="utf-8")
        self._record_count = 0
        self._closed = False

        if self.output_format == "json":
            self._handle.write("[")

    def add_record(self, record: dict[str, Any]) -> None:
        if self.output_format == "json":
            self._write_json_record(record)
            return

        if self.output_format == "markdown":
            self._write_markdown_record(record["input"], record["markdown"])
            return

        self._write_text_record(record["input"], record["text"])

    def add_pdf_record(self, item: InputItem, page_records: Iterable[PDFPageDecision]) -> dict[str, Any]:
        spool = PDFRecordSpool(self._root_dir)
        try:
            for page in page_records:
                spool.append_page(page)
            spool.close()
            pages_with_text = spool.page_count - spool.no_text_pages
            status = "no_text_detected" if spool.page_count and spool.no_text_pages == spool.page_count else "ok"
            reason = NO_VALID_TEXT_REASON if status == "no_text_detected" else None
            message = NO_VALID_TEXT_MESSAGE if status == "no_text_detected" else None
            if self.output_format == "json":
                self._write_pdf_json_record(item, spool)
            elif self.output_format == "markdown":
                self._write_markdown_path(item.display_name, spool.markdown_path)
            else:
                self._write_text_path(item.display_name, spool.text_path)
            return {
                "input": item.display_name,
                "input_type": "pdf",
                "page_count": spool.page_count,
                "pages_with_text": pages_with_text,
                "no_text_pages": spool.no_text_pages,
                "status": status,
                "reason": reason,
                "message": message,
            }
        finally:
            spool.close()
            spool.cleanup()

    def finalize(self, commit: bool) -> None:
        if self._closed:
            return
        self._closed = True

        if self.output_format == "json":
            if self._record_count:
                self._handle.write("\n")
            self._handle.write("]")
        self._handle.flush()
        self._handle.close()

        try:
            if not commit:
                return
            if self.destination:
                path = Path(self.destination)
                path.parent.mkdir(parents=True, exist_ok=True)
                self._output_path.replace(path)
                return
            _copy_output_path_to_stdout(self._output_path)
        finally:
            shutil.rmtree(self._root_dir, ignore_errors=True)

    def _begin_record(self) -> None:
        if self._output_format_is_json():
            if self._record_count:
                self._handle.write(",\n")
            else:
                self._handle.write("\n")
        elif self._record_count:
            self._handle.write("\n\n")
        self._record_count += 1

    def _output_format_is_json(self) -> bool:
        return self.output_format == "json"

    def _write_json_record(self, record: dict[str, Any]) -> None:
        self._begin_record()
        payload = json.dumps(record, ensure_ascii=False, indent=2)
        _write_indented_json_block(self._handle, payload, "  ")

    def _write_text_record(self, input_name: str, content: str) -> None:
        self._begin_record()
        if self.multiple_inputs:
            self._handle.write(f">>> {input_name}")
            if content:
                self._handle.write("\n")
        self._handle.write(content)

    def _write_markdown_record(self, input_name: str, content: str) -> None:
        self._begin_record()
        if self.multiple_inputs:
            self._handle.write(f"## {input_name}")
            if content:
                self._handle.write("\n\n")
        self._handle.write(content)

    def _write_text_path(self, input_name: str, path: Path) -> None:
        self._begin_record()
        has_content = path.stat().st_size > 0
        if self.multiple_inputs:
            self._handle.write(f">>> {input_name}")
            if has_content:
                self._handle.write("\n")
        with path.open("r", encoding="utf-8") as handle:
            _copy_text_stream(handle, self._handle)

    def _write_markdown_path(self, input_name: str, path: Path) -> None:
        self._begin_record()
        has_content = path.stat().st_size > 0
        if self.multiple_inputs:
            self._handle.write(f"## {input_name}")
            if has_content:
                self._handle.write("\n\n")
        with path.open("r", encoding="utf-8") as handle:
            _copy_text_stream(handle, self._handle)

    def _write_pdf_json_record(self, item: InputItem, spool: PDFRecordSpool) -> None:
        self._begin_record()
        pages_with_text = spool.page_count - spool.no_text_pages
        status = "no_text_detected" if spool.page_count and spool.no_text_pages == spool.page_count else "ok"
        reason = NO_VALID_TEXT_REASON if status == "no_text_detected" else None
        message = NO_VALID_TEXT_MESSAGE if status == "no_text_detected" else None
        fields: list[tuple[str, Any]] = [
            ("input", item.display_name),
            ("input_type", "pdf"),
            ("page_count", spool.page_count),
            ("pages_with_text", pages_with_text),
            ("no_text_pages", spool.no_text_pages),
            ("status", status),
            ("reason", reason),
            ("message", message),
        ]

        self._handle.write("  {\n")
        for name, value in fields:
            self._handle.write(f"    {json.dumps(name)}: {json.dumps(value, ensure_ascii=False)},\n")
        self._handle.write('    "text": ')
        _write_json_string_from_file(self._handle, spool.text_path)
        self._handle.write(",\n")
        self._handle.write('    "markdown": ')
        _write_json_string_from_file(self._handle, spool.markdown_path)
        self._handle.write(',\n    "lines": [],\n')
        self._handle.write(f'    "elapsed_seconds": {json.dumps(spool.total_elapsed)},\n')
        self._handle.write('    "visualization_path": null,\n')
        self._handle.write('    "pages": [')

        first_page = True
        with spool.pages_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                payload = line.rstrip("\n")
                if first_page:
                    self._handle.write("\n")
                else:
                    self._handle.write(",\n")
                _write_indented_json_block(self._handle, payload, "      ")
                first_page = False

        if not first_page:
            self._handle.write("\n")
        self._handle.write("    ]\n")
        self._handle.write("  }")
