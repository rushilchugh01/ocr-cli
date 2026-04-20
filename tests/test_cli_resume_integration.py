from __future__ import annotations

import hashlib
import json
import tempfile
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest


class FakeRect:
    def __init__(self, width: float, height: float):
        self.width = width
        self.height = height


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
        self.calls: list[str | bytes] = []

    def __call__(self, source: str | bytes, **_: object):
        self.calls.append(source)
        if not self.results:
            raise AssertionError("Engine was called more times than expected")
        return self.results.pop(0)


class ExplodingEngine:
    def __init__(self, fail_on_call: int):
        self.fail_on_call = fail_on_call
        self.calls: list[str | bytes] = []
        self._count = 0

    def __call__(self, source: str | bytes, **_: object):
        self.calls.append(source)
        self._count += 1
        if self._count == self.fail_on_call:
            raise RuntimeError("simulated OCR crash")
        return FakeResult(f"OCR page {self._count}")


@pytest.fixture()
def system_temp_root(tmp_path, monkeypatch):
    root = tmp_path / "system-temp"
    root.mkdir()
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(root))
    return root


def make_args(input_path: str, output_path: Path | None, **overrides):
    defaults = {
        "verbose": False,
        "log_file": None,
        "input": input_path,
        "pattern": [],
        "recursive": False,
        "format": "json",
        "output": str(output_path) if output_path is not None else None,
        "save_vis": None,
        "fail_fast": False,
        "word_boxes": False,
        "single_char_boxes": False,
        "text_score": None,
        "box_thresh": None,
        "unclip_ratio": None,
        "pages": None,
        "pdf_mode": "auto",
        "pdf_dpi": 144,
        "det_lang": "ch",
        "rec_lang": "devanagari",
        "det_model_type": "mobile",
        "rec_model_type": "mobile",
        "det_version": "ppocrv5",
        "rec_version": "ppocrv5",
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def make_pdf_item(cli_module, source_path: Path):
    return cli_module.InputItem(
        source=str(source_path),
        display_name=str(source_path.resolve()),
        safe_stem=source_path.stem,
    )


def make_image_item(cli_module, source_path: Path):
    return cli_module.InputItem(
        source=str(source_path),
        display_name=str(source_path.resolve()),
        safe_stem=source_path.stem,
    )


def make_pdf_pages(count: int) -> list[FakePage]:
    return [FakePage("\ufffd\ufffd @@ ##", [{"type": 1, "bbox": [0, 0, 100, 100]}]) for _ in range(count)]


def install_fake_pdf_runtime(monkeypatch, pages: list[FakePage]) -> None:
    fake_fitz = types.ModuleType("fitz")
    fake_fitz.open = lambda _: FakeDocument(pages)
    fake_fitz.Matrix = lambda x, y: (x, y)
    monkeypatch.setitem(__import__("sys").modules, "fitz", fake_fitz)


def now_iso(*, hours_ago: int = 0) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()


def args_fingerprint(args: SimpleNamespace) -> dict[str, object]:
    return {
        "format": args.format,
        "pages": args.pages,
        "pdf_mode": args.pdf_mode,
        "pdf_dpi": args.pdf_dpi,
        "det_lang": args.det_lang,
        "rec_lang": args.rec_lang,
        "det_model_type": args.det_model_type,
        "rec_model_type": args.rec_model_type,
        "det_version": args.det_version,
        "rec_version": args.rec_version,
        "word_boxes": args.word_boxes,
        "single_char_boxes": args.single_char_boxes,
        "text_score": args.text_score,
        "box_thresh": args.box_thresh,
        "unclip_ratio": args.unclip_ratio,
    }


def resume_root_for(output_path: Path) -> Path:
    digest = hashlib.sha256(str(output_path.resolve()).encode("utf-8")).hexdigest()
    return Path(tempfile.gettempdir()) / "veridis-ocr-cli" / "resume" / digest


def checkpoint_dir_for(output_path: Path, source_path: Path) -> Path:
    digest = hashlib.sha256(str(source_path.resolve()).encode("utf-8")).hexdigest()
    return resume_root_for(output_path) / "inputs" / digest


def seed_manifest(output_path: Path, source_paths: list[Path], args: SimpleNamespace, *, updated_at: str) -> Path:
    root = resume_root_for(output_path)
    root.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "output_path": str(output_path.resolve()),
        "updated_at": updated_at,
        "fingerprint": args_fingerprint(args),
        "inputs": [str(path.resolve()) for path in source_paths],
    }
    (root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return root


def make_pdf_page_payload(page_number: int, text: str) -> dict[str, object]:
    return {
        "page_number": page_number,
        "status": "ok",
        "reason": None,
        "message": None,
        "method_used": "ocr",
        "text": text,
        "markdown": text,
        "lines": [],
        "elapsed_seconds": 0.5,
        "native_text_found": False,
        "native_text_accepted": False,
        "native_text_score": 0.0,
        "decision": "fallback_to_ocr",
        "fallback_reason": "garbled_or_missing_native_text",
        "quality_metrics": {"char_count": len(text), "text_coverage": 0.0, "image_coverage": 1.0},
        "visualization_path": None,
    }


def seed_pdf_checkpoint(
    output_path: Path,
    item,
    args: SimpleNamespace,
    *,
    updated_at: str,
    selected_pages: list[int],
    completed_pages: list[dict[str, object]],
    status: str = "in_progress",
) -> Path:
    root = seed_manifest(output_path, [Path(item.source)], args, updated_at=updated_at)
    checkpoint_dir = checkpoint_dir_for(output_path, Path(item.source))
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    state = {
        "source": str(Path(item.source).resolve()),
        "display_name": item.display_name,
        "input_type": "pdf",
        "status": status,
        "updated_at": updated_at,
        "selected_pages": selected_pages,
        "completed_pages": [page["page_number"] for page in completed_pages],
    }
    (checkpoint_dir / "state.json").write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    with (checkpoint_dir / "pages.jsonl").open("w", encoding="utf-8") as handle:
        for page in completed_pages:
            handle.write(json.dumps(page, ensure_ascii=False))
            handle.write("\n")
    return root


def seed_image_checkpoint(output_path: Path, item, args: SimpleNamespace, *, updated_at: str, record: dict[str, object]) -> Path:
    root = seed_manifest(output_path, [Path(item.source)], args, updated_at=updated_at)
    checkpoint_dir = checkpoint_dir_for(output_path, Path(item.source))
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    state = {
        "source": str(Path(item.source).resolve()),
        "display_name": item.display_name,
        "input_type": "image",
        "status": "complete",
        "updated_at": updated_at,
        "record_path": "record.json",
    }
    (checkpoint_dir / "state.json").write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    (checkpoint_dir / "record.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return root


def load_single_json_record(output_path: Path) -> dict[str, object]:
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert len(payload) == 1
    return payload[0]


def page_numbers(record: dict[str, object]) -> list[int]:
    return [page["page_number"] for page in record["pages"]]


def test_run_ocr_auto_resumes_recent_partial_pdf_checkpoint(
    cli_module,
    monkeypatch,
    tmp_path,
    system_temp_root,
    capsys,
):
    monkeypatch.setattr(cli_module, "configure_logging", lambda *args, **kwargs: None)

    source_path = tmp_path / "sample.pdf"
    source_path.write_bytes(b"%PDF-1.7\n")
    output_path = tmp_path / "result.json"
    item = make_pdf_item(cli_module, source_path)
    args = make_args(str(source_path), output_path)

    install_fake_pdf_runtime(monkeypatch, make_pdf_pages(4))
    engine = FakeEngine(
        [
            FakeResult("OCR page 3"),
            FakeResult("OCR page 4"),
        ]
    )
    monkeypatch.setattr(cli_module, "build_engine", lambda *args, **kwargs: engine)
    monkeypatch.setattr(cli_module, "resolve_inputs", lambda *args, **kwargs: [item])
    monkeypatch.setattr(cli_module, "is_pdf_source", lambda source: source.endswith(".pdf"))

    seed_pdf_checkpoint(
        output_path,
        item,
        args,
        updated_at=now_iso(hours_ago=2),
        selected_pages=[1, 2, 3, 4],
        completed_pages=[make_pdf_page_payload(1, "OCR page 1"), make_pdf_page_payload(2, "OCR page 2")],
    )

    assert cli_module.run_ocr(args) == 0

    record = load_single_json_record(output_path)
    assert page_numbers(record) == [1, 2, 3, 4]
    assert [page["text"] for page in record["pages"]] == ["OCR page 1", "OCR page 2", "OCR page 3", "OCR page 4"]
    assert len(engine.calls) == 2
    assert "resum" in capsys.readouterr().err.lower()


def test_run_ocr_resume_ignores_truncated_last_jsonl_line(
    cli_module,
    monkeypatch,
    tmp_path,
    system_temp_root,
):
    monkeypatch.setattr(cli_module, "configure_logging", lambda *args, **kwargs: None)

    source_path = tmp_path / "sample.pdf"
    source_path.write_bytes(b"%PDF-1.7\n")
    output_path = tmp_path / "result.json"
    item = make_pdf_item(cli_module, source_path)
    args = make_args(str(source_path), output_path)

    install_fake_pdf_runtime(monkeypatch, make_pdf_pages(4))
    engine = FakeEngine(
        [
            FakeResult("OCR page 2"),
            FakeResult("OCR page 3"),
            FakeResult("OCR page 4"),
        ]
    )
    monkeypatch.setattr(cli_module, "build_engine", lambda *args, **kwargs: engine)
    monkeypatch.setattr(cli_module, "resolve_inputs", lambda *args, **kwargs: [item])
    monkeypatch.setattr(cli_module, "is_pdf_source", lambda source: source.endswith(".pdf"))

    seed_pdf_checkpoint(
        output_path,
        item,
        args,
        updated_at=now_iso(hours_ago=1),
        selected_pages=[1, 2, 3, 4],
        completed_pages=[make_pdf_page_payload(1, "OCR page 1")],
    )
    checkpoint_dir = checkpoint_dir_for(output_path, Path(item.source))
    with (checkpoint_dir / "pages.jsonl").open("a", encoding="utf-8") as handle:
        handle.write('{"page_number": 2, "status": "ok"')

    assert cli_module.run_ocr(args) == 0

    record = load_single_json_record(output_path)
    assert page_numbers(record) == [1, 2, 3, 4]
    assert len(engine.calls) == 3


def test_run_ocr_ignores_stale_checkpoint_and_starts_fresh(
    cli_module,
    monkeypatch,
    tmp_path,
    system_temp_root,
    capsys,
):
    monkeypatch.setattr(cli_module, "configure_logging", lambda *args, **kwargs: None)

    source_path = tmp_path / "sample.pdf"
    source_path.write_bytes(b"%PDF-1.7\n")
    output_path = tmp_path / "result.json"
    item = make_pdf_item(cli_module, source_path)
    args = make_args(str(source_path), output_path)

    install_fake_pdf_runtime(monkeypatch, make_pdf_pages(4))
    engine = FakeEngine(
        [
            FakeResult("OCR page 1"),
            FakeResult("OCR page 2"),
            FakeResult("OCR page 3"),
            FakeResult("OCR page 4"),
        ]
    )
    monkeypatch.setattr(cli_module, "build_engine", lambda *args, **kwargs: engine)
    monkeypatch.setattr(cli_module, "resolve_inputs", lambda *args, **kwargs: [item])
    monkeypatch.setattr(cli_module, "is_pdf_source", lambda source: source.endswith(".pdf"))

    seed_pdf_checkpoint(
        output_path,
        item,
        args,
        updated_at=now_iso(hours_ago=49),
        selected_pages=[1, 2, 3, 4],
        completed_pages=[make_pdf_page_payload(1, "old page 1"), make_pdf_page_payload(2, "old page 2")],
    )

    assert cli_module.run_ocr(args) == 0

    record = load_single_json_record(output_path)
    assert [page["text"] for page in record["pages"]] == ["OCR page 1", "OCR page 2", "OCR page 3", "OCR page 4"]
    assert len(engine.calls) == 4
    stderr = capsys.readouterr().err.lower()
    assert "stale" in stderr
    assert "fresh" in stderr


def test_run_ocr_ignores_manifest_mismatch_and_starts_fresh(
    cli_module,
    monkeypatch,
    tmp_path,
    system_temp_root,
    capsys,
):
    monkeypatch.setattr(cli_module, "configure_logging", lambda *args, **kwargs: None)

    source_path = tmp_path / "sample.pdf"
    source_path.write_bytes(b"%PDF-1.7\n")
    output_path = tmp_path / "result.json"
    item = make_pdf_item(cli_module, source_path)
    args = make_args(str(source_path), output_path, pdf_dpi=144)
    mismatched_args = make_args(str(source_path), output_path, pdf_dpi=200)

    install_fake_pdf_runtime(monkeypatch, make_pdf_pages(4))
    engine = FakeEngine(
        [
            FakeResult("OCR page 1"),
            FakeResult("OCR page 2"),
            FakeResult("OCR page 3"),
            FakeResult("OCR page 4"),
        ]
    )
    monkeypatch.setattr(cli_module, "build_engine", lambda *args, **kwargs: engine)
    monkeypatch.setattr(cli_module, "resolve_inputs", lambda *args, **kwargs: [item])
    monkeypatch.setattr(cli_module, "is_pdf_source", lambda source: source.endswith(".pdf"))

    seed_pdf_checkpoint(
        output_path,
        item,
        mismatched_args,
        updated_at=now_iso(hours_ago=1),
        selected_pages=[1, 2, 3, 4],
        completed_pages=[make_pdf_page_payload(1, "old page 1"), make_pdf_page_payload(2, "old page 2")],
    )

    assert cli_module.run_ocr(args) == 0

    record = load_single_json_record(output_path)
    assert [page["text"] for page in record["pages"]] == ["OCR page 1", "OCR page 2", "OCR page 3", "OCR page 4"]
    assert len(engine.calls) == 4
    stderr = capsys.readouterr().err.lower()
    assert "checkpoint" in stderr
    assert "fresh" in stderr


def test_run_ocr_corrupt_checkpoint_falls_back_to_fresh_run(
    cli_module,
    monkeypatch,
    tmp_path,
    system_temp_root,
    capsys,
):
    monkeypatch.setattr(cli_module, "configure_logging", lambda *args, **kwargs: None)

    source_path = tmp_path / "sample.pdf"
    source_path.write_bytes(b"%PDF-1.7\n")
    output_path = tmp_path / "result.json"
    item = make_pdf_item(cli_module, source_path)
    args = make_args(str(source_path), output_path)

    install_fake_pdf_runtime(monkeypatch, make_pdf_pages(4))
    engine = FakeEngine(
        [
            FakeResult("OCR page 1"),
            FakeResult("OCR page 2"),
            FakeResult("OCR page 3"),
            FakeResult("OCR page 4"),
        ]
    )
    monkeypatch.setattr(cli_module, "build_engine", lambda *args, **kwargs: engine)
    monkeypatch.setattr(cli_module, "resolve_inputs", lambda *args, **kwargs: [item])
    monkeypatch.setattr(cli_module, "is_pdf_source", lambda source: source.endswith(".pdf"))

    seed_manifest(output_path, [source_path], args, updated_at=now_iso(hours_ago=1))
    checkpoint_dir = checkpoint_dir_for(output_path, source_path)
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    (checkpoint_dir / "state.json").write_text("{not valid json", encoding="utf-8")
    (checkpoint_dir / "pages.jsonl").write_text("", encoding="utf-8")

    assert cli_module.run_ocr(args) == 0

    record = load_single_json_record(output_path)
    assert [page["text"] for page in record["pages"]] == ["OCR page 1", "OCR page 2", "OCR page 3", "OCR page 4"]
    assert len(engine.calls) == 4
    stderr = capsys.readouterr().err.lower()
    assert "checkpoint" in stderr
    assert "fresh" in stderr


def test_run_ocr_skips_completed_image_record_from_checkpoint(
    cli_module,
    monkeypatch,
    tmp_path,
    system_temp_root,
    capsys,
):
    monkeypatch.setattr(cli_module, "configure_logging", lambda *args, **kwargs: None)

    source_path = tmp_path / "tree.jpg"
    source_path.write_bytes(b"fake-image")
    output_path = tmp_path / "result.json"
    item = make_image_item(cli_module, source_path)
    args = make_args(str(source_path), output_path)

    monkeypatch.setattr(cli_module, "build_engine", lambda *args, **kwargs: object())
    monkeypatch.setattr(cli_module, "resolve_inputs", lambda *args, **kwargs: [item])
    monkeypatch.setattr(cli_module, "is_pdf_source", lambda source: False)
    image_calls: list[str | bytes] = []

    def fake_run_ocr_for_source(*args, **kwargs):
        image_calls.append(args[1])
        return FakeResult("fresh OCR result")

    monkeypatch.setattr(cli_module, "run_ocr_for_source", fake_run_ocr_for_source)

    saved_record = {
        "input": item.display_name,
        "input_type": "image",
        "status": "ok",
        "reason": None,
        "message": None,
        "method_used": "ocr",
        "text": "checkpoint text",
        "markdown": "checkpoint text",
        "lines": [],
        "elapsed_seconds": 0.1,
        "visualization_path": None,
    }
    seed_image_checkpoint(output_path, item, args, updated_at=now_iso(hours_ago=1), record=saved_record)

    assert cli_module.run_ocr(args) == 0

    assert image_calls == []
    assert load_single_json_record(output_path) == saved_record
    assert "resum" in capsys.readouterr().err.lower()


def test_run_ocr_skips_completed_pdf_checkpoint(
    cli_module,
    monkeypatch,
    tmp_path,
    system_temp_root,
):
    monkeypatch.setattr(cli_module, "configure_logging", lambda *args, **kwargs: None)

    source_path = tmp_path / "sample.pdf"
    source_path.write_bytes(b"%PDF-1.7\n")
    output_path = tmp_path / "result.json"
    item = make_pdf_item(cli_module, source_path)
    args = make_args(str(source_path), output_path)

    install_fake_pdf_runtime(monkeypatch, make_pdf_pages(2))
    engine = FakeEngine([FakeResult("OCR page 1"), FakeResult("OCR page 2")])
    monkeypatch.setattr(cli_module, "build_engine", lambda *args, **kwargs: engine)
    monkeypatch.setattr(cli_module, "resolve_inputs", lambda *args, **kwargs: [item])
    monkeypatch.setattr(cli_module, "is_pdf_source", lambda source: source.endswith(".pdf"))

    seed_pdf_checkpoint(
        output_path,
        item,
        args,
        updated_at=now_iso(hours_ago=1),
        selected_pages=[1, 2],
        completed_pages=[make_pdf_page_payload(1, "OCR page 1"), make_pdf_page_payload(2, "OCR page 2")],
        status="complete",
    )

    assert cli_module.run_ocr(args) == 0

    record = load_single_json_record(output_path)
    assert page_numbers(record) == [1, 2]
    assert [page["text"] for page in record["pages"]] == ["OCR page 1", "OCR page 2"]
    assert len(engine.calls) == 0


def test_run_ocr_failure_leaves_checkpoint_and_does_not_commit_output(
    cli_module,
    monkeypatch,
    tmp_path,
    system_temp_root,
):
    monkeypatch.setattr(cli_module, "configure_logging", lambda *args, **kwargs: None)

    source_path = tmp_path / "sample.pdf"
    source_path.write_bytes(b"%PDF-1.7\n")
    output_path = tmp_path / "result.json"
    item = make_pdf_item(cli_module, source_path)
    args = make_args(str(source_path), output_path)

    install_fake_pdf_runtime(monkeypatch, make_pdf_pages(3))
    engine = ExplodingEngine(fail_on_call=3)
    monkeypatch.setattr(cli_module, "build_engine", lambda *args, **kwargs: engine)
    monkeypatch.setattr(cli_module, "resolve_inputs", lambda *args, **kwargs: [item])
    monkeypatch.setattr(cli_module, "is_pdf_source", lambda source: source.endswith(".pdf"))

    assert cli_module.run_ocr(args) == 2
    assert not output_path.exists()

    checkpoint_dir = checkpoint_dir_for(output_path, source_path)
    assert checkpoint_dir.exists()
    lines = (checkpoint_dir / "pages.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2


def test_run_ocr_successful_resume_cleans_checkpoint_root(
    cli_module,
    monkeypatch,
    tmp_path,
    system_temp_root,
):
    monkeypatch.setattr(cli_module, "configure_logging", lambda *args, **kwargs: None)

    source_path = tmp_path / "sample.pdf"
    source_path.write_bytes(b"%PDF-1.7\n")
    output_path = tmp_path / "result.json"
    item = make_pdf_item(cli_module, source_path)
    args = make_args(str(source_path), output_path)

    install_fake_pdf_runtime(monkeypatch, make_pdf_pages(4))
    engine = FakeEngine(
        [
            FakeResult("OCR page 1"),
            FakeResult("OCR page 2"),
            FakeResult("OCR page 3"),
            FakeResult("OCR page 4"),
        ]
    )
    monkeypatch.setattr(cli_module, "build_engine", lambda *args, **kwargs: engine)
    monkeypatch.setattr(cli_module, "resolve_inputs", lambda *args, **kwargs: [item])
    monkeypatch.setattr(cli_module, "is_pdf_source", lambda source: source.endswith(".pdf"))

    root = seed_pdf_checkpoint(
        output_path,
        item,
        args,
        updated_at=now_iso(hours_ago=2),
        selected_pages=[1, 2, 3, 4],
        completed_pages=[make_pdf_page_payload(1, "OCR page 1"), make_pdf_page_payload(2, "OCR page 2")],
    )

    assert cli_module.run_ocr(args) == 0
    assert not root.exists()


def test_run_ocr_without_output_does_not_create_durable_resume_checkpoint(
    cli_module,
    monkeypatch,
    tmp_path,
    system_temp_root,
):
    monkeypatch.setattr(cli_module, "configure_logging", lambda *args, **kwargs: None)

    source_path = tmp_path / "sample.pdf"
    source_path.write_bytes(b"%PDF-1.7\n")
    item = make_pdf_item(cli_module, source_path)
    args = make_args(str(source_path), None)

    install_fake_pdf_runtime(monkeypatch, make_pdf_pages(2))
    engine = FakeEngine([FakeResult("OCR page 1"), FakeResult("OCR page 2")])
    monkeypatch.setattr(cli_module, "build_engine", lambda *args, **kwargs: engine)
    monkeypatch.setattr(cli_module, "resolve_inputs", lambda *args, **kwargs: [item])
    monkeypatch.setattr(cli_module, "is_pdf_source", lambda source: source.endswith(".pdf"))

    assert cli_module.run_ocr(args) == 0
    assert len(engine.calls) == 2
    assert not (system_temp_root / "veridis-ocr-cli" / "resume").exists()
