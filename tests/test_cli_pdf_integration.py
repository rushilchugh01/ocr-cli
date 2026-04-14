from __future__ import annotations

import sys
import types
from dataclasses import dataclass
from types import SimpleNamespace


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
