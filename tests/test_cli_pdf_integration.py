from __future__ import annotations

import json
import sys
import types
from dataclasses import dataclass
from types import SimpleNamespace

import pytest


@dataclass
class FakeRect:
    width: float
    height: float


class FakePixmap:
    def tobytes(self, fmt: str) -> bytes:
        assert fmt == "png"
        return b"fake-png"


class FakePage:
    def __init__(self, native_text: str, blocks: list[dict[str, object]]):
        self.native_text = native_text
        self.blocks = blocks
        self.rect = FakeRect(width=100.0, height=100.0)

    def get_text(self, mode: str):
        if mode == "text":
            return self.native_text
        if mode == "dict":
            return {"blocks": self.blocks}
        raise AssertionError(f"Unexpected mode: {mode}")

    def get_pixmap(self, matrix, alpha: bool):
        assert alpha is False
        return FakePixmap()


class FakeDocument:
    def __init__(self, pages: list[FakePage]):
        self.pages = pages
        self.page_count = len(pages)

    def load_page(self, index: int) -> FakePage:
        return self.pages[index]

    def close(self) -> None:
        return None


class FakeResult:
    def __init__(self, text: str, elapsed: float = 0.25):
        self.text = text
        self.elapse = elapsed
        self.word_results = None

    def to_json(self):
        if not self.text:
            return []
        return [{"txt": self.text, "box": [[0, 0], [1, 0], [1, 1], [0, 1]], "score": 0.98}]

    def to_markdown(self):
        return self.text

    def vis(self, _: str):
        return None


class FakeEngine:
    def __init__(self, results: list[FakeResult]):
        self.results = results
        self.calls: list[str] = []

    def __call__(self, source: str, **_: object):
        self.calls.append(source)
        return self.results.pop(0)


def make_args(**overrides):
    defaults = {
        "word_boxes": False,
        "single_char_boxes": False,
        "text_score": None,
        "box_thresh": None,
        "unclip_ratio": None,
        "save_vis": None,
        "pages": None,
        "pdf_mode": "auto",
        "pdf_dpi": 144,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_process_pdf_input_uses_native_text_then_ocr_fallback(cli_module, monkeypatch):
    pages = [
        FakePage(
            "Invoice Total 1000\nPaid on 2026-04-14",
            [{"type": 0, "bbox": [0, 0, 80, 60]}],
        ),
        FakePage(
            "\ufffd\ufffd \ufffd\ufffd @@ ## \ufffd\ufffd",
            [{"type": 1, "bbox": [0, 0, 100, 100]}],
        ),
    ]
    fake_fitz = types.ModuleType("fitz")
    fake_fitz.open = lambda _: FakeDocument(pages)
    fake_fitz.Matrix = lambda x, y: (x, y)
    monkeypatch.setitem(sys.modules, "fitz", fake_fitz)

    engine = FakeEngine([FakeResult("OCR fallback text")])
    item = cli_module.InputItem(source="C:/docs/sample.pdf", display_name="C:/docs/sample.pdf", safe_stem="sample")

    record = cli_module.process_pdf_input(item, engine, make_args(), multiple_inputs=False)

    assert record["input_type"] == "pdf"
    assert record["page_count"] == 2
    assert record["pages"][0]["method_used"] == "native_text"
    assert record["pages"][0]["text"] == "Invoice Total 1000\nPaid on 2026-04-14"
    assert record["pages"][1]["method_used"] == "ocr"
    assert record["pages"][1]["fallback_reason"] == "garbled_or_missing_native_text"
    assert record["pages"][1]["text"] == "OCR fallback text"
    assert record["pages"][1]["reason"] is None
    assert record["pages"][1]["message"] is None
    assert len(engine.calls) == 1


def test_process_pdf_input_honors_page_selection(cli_module, monkeypatch):
    pages = [
        FakePage("Page 1 text", [{"type": 0, "bbox": [0, 0, 80, 60]}]),
        FakePage("Page 2 text", [{"type": 0, "bbox": [0, 0, 80, 60]}]),
        FakePage("Page 3 text", [{"type": 0, "bbox": [0, 0, 80, 60]}]),
    ]
    fake_fitz = types.ModuleType("fitz")
    fake_fitz.open = lambda _: FakeDocument(pages)
    fake_fitz.Matrix = lambda x, y: (x, y)
    monkeypatch.setitem(sys.modules, "fitz", fake_fitz)

    engine = FakeEngine([])
    item = cli_module.InputItem(source="C:/docs/sample.pdf", display_name="C:/docs/sample.pdf", safe_stem="sample")

    record = cli_module.process_pdf_input(item, engine, make_args(pages="2-3"), multiple_inputs=False)

    assert [page["page_number"] for page in record["pages"]] == [2, 3]
    assert all(page["method_used"] == "native_text" for page in record["pages"])
    assert engine.calls == []


def test_rasterize_pdf_page_rejects_oversized_raster_before_pixmap(cli_module, monkeypatch):
    class OversizedPage:
        def __init__(self):
            self.rect = FakeRect(width=6000.0, height=6000.0)

        def get_pixmap(self, matrix, alpha: bool):
            raise AssertionError("get_pixmap should not be called for an oversized raster")

    fake_fitz = types.ModuleType("fitz")
    fake_fitz.Matrix = lambda x, y: (x, y)
    monkeypatch.setitem(sys.modules, "fitz", fake_fitz)

    with pytest.raises(cli_module.CLIError, match="Requested PDF raster is too large"):
        cli_module.rasterize_pdf_page(OversizedPage(), 144)


def test_run_ocr_writes_pdf_json_output_via_spooler(cli_module, monkeypatch, tmp_path):
    monkeypatch.setattr(cli_module, "configure_logging", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli_module, "build_engine", lambda *args, **kwargs: object())
    item = cli_module.InputItem(source="C:/docs/sample.pdf", display_name="C:/docs/sample.pdf", safe_stem="sample")
    monkeypatch.setattr(cli_module, "resolve_inputs", lambda *args, **kwargs: [item])
    monkeypatch.setattr(cli_module, "is_pdf_source", lambda source: source.endswith(".pdf"))

    def make_page(page_number: int, text: str, method_used: str) -> object:
        quality = {
            "normalized_text": text if method_used == "native_text" else "",
            "accepted": method_used == "native_text",
            "score": 0.8 if method_used == "native_text" else 0.2,
            "decision": "use_native_text" if method_used == "native_text" else "fallback_to_ocr",
            "metrics": {"char_count": len(text), "text_coverage": 0.5, "image_coverage": 0.0},
        }
        return cli_module.build_pdf_page_record(
            item=item,
            page_number=page_number,
            quality=quality,
            method_used=method_used,
            text=text,
            markdown=text,
            lines=[],
            elapsed_seconds=0.5,
            visualization_path=None,
            fallback_reason=None if method_used == "native_text" else "garbled_or_missing_native_text",
        )

    monkeypatch.setattr(
        cli_module,
        "iter_pdf_page_records",
        lambda *args, **kwargs: iter(
            [
                make_page(1, "Page 1 text", "native_text"),
                make_page(2, "OCR fallback text", "ocr"),
            ]
        ),
    )

    output_path = tmp_path / "result.json"
    args = SimpleNamespace(
        verbose=False,
        log_file=None,
        input="ignored",
        pattern=[],
        recursive=False,
        format="json",
        output=str(output_path),
        save_vis=None,
        fail_fast=False,
        word_boxes=False,
        single_char_boxes=False,
        text_score=None,
        box_thresh=None,
        unclip_ratio=None,
        pages=None,
        pdf_mode="auto",
        pdf_dpi=144,
    )

    assert cli_module.run_ocr(args) == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert len(payload) == 1
    record = payload[0]
    assert record["input_type"] == "pdf"
    assert record["page_count"] == 2
    assert record["pages_with_text"] == 2
    assert record["no_text_pages"] == 0
    assert record["reason"] is None
    assert record["message"] is None
    assert record["pages"][0]["page_number"] == 1
    assert record["pages"][1]["method_used"] == "ocr"
    assert "--- Page 1 ---" in record["text"]
    assert "OCR fallback text" in record["markdown"]


def test_run_ocr_writes_empty_text_output_and_notice(cli_module, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli_module, "configure_logging", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli_module, "build_engine", lambda *args, **kwargs: object())
    item = cli_module.InputItem(source="C:/docs/tree.jpg", display_name="C:/docs/tree.jpg", safe_stem="tree")
    monkeypatch.setattr(cli_module, "resolve_inputs", lambda *args, **kwargs: [item])
    monkeypatch.setattr(cli_module, "is_pdf_source", lambda source: False)

    class EmptyResult:
        elapse = 0.0
        word_results = [[]]

        @staticmethod
        def to_json():
            return []

        @staticmethod
        def to_markdown():
            return "没有检测到任何文本。"

        @staticmethod
        def vis(_: str):
            return None

    monkeypatch.setattr(cli_module, "run_ocr_for_source", lambda *args, **kwargs: EmptyResult())

    output_path = tmp_path / "result.txt"
    args = SimpleNamespace(
        verbose=False,
        log_file=None,
        input="ignored",
        pattern=[],
        recursive=False,
        format="text",
        output=str(output_path),
        save_vis=None,
        fail_fast=False,
        word_boxes=False,
        single_char_boxes=False,
        text_score=None,
        box_thresh=None,
        unclip_ratio=None,
        pages=None,
        pdf_mode="auto",
        pdf_dpi=144,
    )

    assert cli_module.run_ocr(args) == 0
    captured = capsys.readouterr()
    assert output_path.read_text(encoding="utf-8") == ""
    assert captured.out == ""
    assert captured.err == "No valid text detected: C:/docs/tree.jpg\n"
