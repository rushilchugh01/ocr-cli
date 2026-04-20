from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from json import JSONDecodeError
from pathlib import Path
from typing import Any, Sequence

from rapidocr_cli.inputs import is_url
from rapidocr_cli.output import build_pdf_page_payload, parse_pdf_page_payload
from rapidocr_cli.types import InputItem, PDFPageDecision


SCHEMA_VERSION = 1
STALE_AFTER = timedelta(days=2)


@dataclass(frozen=True)
class PDFResumeState:
    selected_pages: list[int]
    restored_pages: list[PDFPageDecision]
    remaining_pages: list[int]

    @property
    def is_complete(self) -> bool:
        return not self.remaining_pages


def build_resume_fingerprint(args: Any) -> dict[str, Any]:
    return {
        "format": getattr(args, "format", None),
        "pages": getattr(args, "pages", None),
        "pdf_mode": getattr(args, "pdf_mode", None),
        "pdf_dpi": getattr(args, "pdf_dpi", None),
        "det_lang": getattr(args, "det_lang", None),
        "rec_lang": getattr(args, "rec_lang", None),
        "det_model_type": getattr(args, "det_model_type", None),
        "rec_model_type": getattr(args, "rec_model_type", None),
        "det_version": getattr(args, "det_version", None),
        "rec_version": getattr(args, "rec_version", None),
        "word_boxes": getattr(args, "word_boxes", None),
        "single_char_boxes": getattr(args, "single_char_boxes", None),
        "text_score": getattr(args, "text_score", None),
        "box_thresh": getattr(args, "box_thresh", None),
        "unclip_ratio": getattr(args, "unclip_ratio", None),
    }


def resume_root_for_output(destination: str) -> Path:
    output_path = Path(destination).resolve()
    digest = hashlib.sha256(str(output_path).encode("utf-8")).hexdigest()
    return Path(tempfile.gettempdir()) / "veridis-ocr-cli" / "resume" / digest


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().isoformat()


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _source_identity(source: str) -> str:
    if is_url(source):
        return source
    return str(Path(source).resolve())


def _item_identity(item: InputItem) -> str:
    return _source_identity(item.source)


def _item_digest(item: InputItem) -> str:
    return hashlib.sha256(_item_identity(item).encode("utf-8")).hexdigest()


def _write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(path)


class ResumeManager:
    def __init__(self, root: Path, output_path: Path, fingerprint: dict[str, Any], input_identities: list[str]):
        self.root = root
        self.output_path = output_path
        self.manifest_path = root / "manifest.json"
        self._fingerprint = fingerprint
        self._input_identities = input_identities
        self._pdf_completed_pages: dict[str, list[int]] = {}
        self._resume_noted: set[str] = set()
        self._initialize()

    @classmethod
    def from_run(cls, args: Any, inputs: Sequence[InputItem]) -> ResumeManager | None:
        if not getattr(args, "output", None):
            return None
        output_path = Path(args.output).resolve()
        root = resume_root_for_output(args.output)
        input_identities = [_item_identity(item) for item in inputs]
        return cls(root, output_path, build_resume_fingerprint(args), input_identities)

    def has_checkpoint(self, item: InputItem) -> bool:
        input_dir = self._input_dir(item)
        return (input_dir / "state.json").exists() or (input_dir / "pages.jsonl").exists()

    def restore_image_record(self, item: InputItem) -> dict[str, Any] | None:
        try:
            state = self._load_item_state(item)
        except Exception:
            self._discard_item_checkpoint(item, f"Ignoring checkpoint for {item.display_name} and starting fresh.")
            return None
        if state is None:
            if self._input_dir(item).exists():
                self._discard_item_checkpoint(item, f"Ignoring checkpoint for {item.display_name} and starting fresh.")
            return None
        if state.get("input_type") != "image":
            self._discard_item_checkpoint(item, f"Ignoring checkpoint for {item.display_name} and starting fresh.")
            return None
        if state.get("status") != "complete":
            self._discard_item_checkpoint(item, f"Ignoring checkpoint for {item.display_name} and starting fresh.")
            return None
        record_path = self._input_dir(item) / str(state.get("record_path") or "record.json")
        try:
            record = json.loads(record_path.read_text(encoding="utf-8"))
        except Exception:
            self._discard_item_checkpoint(item, f"Ignoring checkpoint for {item.display_name} and starting fresh.")
            return None
        self._note_resume(item)
        return record

    def prepare_pdf(self, item: InputItem, selected_pages: list[int]) -> PDFResumeState:
        try:
            state = self._load_item_state(item)
        except Exception:
            self._discard_item_checkpoint(item, f"Ignoring checkpoint for {item.display_name} and starting fresh.")
            self._pdf_completed_pages[_item_digest(item)] = []
            return PDFResumeState(selected_pages=selected_pages, restored_pages=[], remaining_pages=list(selected_pages))
        if state is None:
            if self._input_dir(item).exists():
                self._discard_item_checkpoint(item, f"Ignoring checkpoint for {item.display_name} and starting fresh.")
            self._pdf_completed_pages[_item_digest(item)] = []
            return PDFResumeState(selected_pages=selected_pages, restored_pages=[], remaining_pages=list(selected_pages))

        if state.get("input_type") != "pdf":
            self._discard_item_checkpoint(item, f"Ignoring checkpoint for {item.display_name} and starting fresh.")
            self._pdf_completed_pages[_item_digest(item)] = []
            return PDFResumeState(selected_pages=selected_pages, restored_pages=[], remaining_pages=list(selected_pages))

        saved_selected_pages = list(state.get("selected_pages") or [])
        if saved_selected_pages and saved_selected_pages != selected_pages:
            self._discard_item_checkpoint(item, f"Ignoring checkpoint for {item.display_name} and starting fresh.")
            self._pdf_completed_pages[_item_digest(item)] = []
            return PDFResumeState(selected_pages=selected_pages, restored_pages=[], remaining_pages=list(selected_pages))

        pages_path = self._input_dir(item) / "pages.jsonl"
        try:
            restored_pages = self._load_pdf_pages(pages_path)
        except Exception:
            self._discard_item_checkpoint(item, f"Ignoring checkpoint for {item.display_name} and starting fresh.")
            self._pdf_completed_pages[_item_digest(item)] = []
            return PDFResumeState(selected_pages=selected_pages, restored_pages=[], remaining_pages=list(selected_pages))

        restored_by_page = {page.page_number: page for page in restored_pages}
        ordered_restored = [restored_by_page[page_number] for page_number in selected_pages if page_number in restored_by_page]
        completed_pages = [page.page_number for page in ordered_restored]
        remaining_pages = [page_number for page_number in selected_pages if page_number not in restored_by_page]

        if state.get("status") == "complete" and remaining_pages:
            self._discard_item_checkpoint(item, f"Ignoring checkpoint for {item.display_name} and starting fresh.")
            self._pdf_completed_pages[_item_digest(item)] = []
            return PDFResumeState(selected_pages=selected_pages, restored_pages=[], remaining_pages=list(selected_pages))

        self._pdf_completed_pages[_item_digest(item)] = completed_pages
        self._write_pdf_state(
            item,
            selected_pages=selected_pages,
            completed_pages=completed_pages,
            status="complete" if not remaining_pages else "in_progress",
        )
        if ordered_restored:
            self._note_resume(item)
        return PDFResumeState(selected_pages=selected_pages, restored_pages=ordered_restored, remaining_pages=remaining_pages)

    def append_pdf_page(self, item: InputItem, selected_pages: list[int] | None, page: PDFPageDecision) -> None:
        input_dir = self._input_dir(item)
        input_dir.mkdir(parents=True, exist_ok=True)
        pages_path = input_dir / "pages.jsonl"
        with pages_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(build_pdf_page_payload(page), ensure_ascii=False))
            handle.write("\n")
            handle.flush()
            if hasattr(os, "fsync"):
                os.fsync(handle.fileno())

        key = _item_digest(item)
        completed_pages = list(self._pdf_completed_pages.get(key, []))
        if page.page_number not in completed_pages:
            completed_pages.append(page.page_number)
            completed_pages.sort()
        self._pdf_completed_pages[key] = completed_pages
        status = "in_progress"
        if selected_pages is not None and len(completed_pages) >= len(selected_pages):
            status = "complete"
        self._write_pdf_state(item, selected_pages=selected_pages, completed_pages=completed_pages, status=status)

    def complete_pdf(self, item: InputItem, selected_pages: list[int]) -> None:
        completed_pages = list(self._pdf_completed_pages.get(_item_digest(item), []))
        self._write_pdf_state(item, selected_pages=selected_pages, completed_pages=completed_pages, status="complete")

    def save_image_record(self, item: InputItem, record: dict[str, Any]) -> None:
        input_dir = self._input_dir(item)
        input_dir.mkdir(parents=True, exist_ok=True)
        _write_json_atomic(input_dir / "record.json", record)
        _write_json_atomic(
            input_dir / "state.json",
            {
                "source": _item_identity(item),
                "display_name": item.display_name,
                "input_type": "image",
                "status": "complete",
                "updated_at": _utc_now_iso(),
                "record_path": "record.json",
            },
        )
        self._touch_manifest()

    def cleanup(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def _initialize(self) -> None:
        if not self.root.exists():
            self._write_manifest()
            return

        try:
            manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except Exception:
            self._reset_root("Ignoring checkpoint because it could not be read; starting fresh.")
            return

        try:
            updated_at = _parse_timestamp(str(manifest["updated_at"]))
        except Exception:
            self._reset_root("Ignoring checkpoint because it could not be read; starting fresh.")
            return

        if _utc_now() - updated_at > STALE_AFTER:
            self._reset_root(f"Ignoring stale checkpoint at {self.root} and starting fresh.")
            return

        expected = {
            "schema_version": SCHEMA_VERSION,
            "output_path": str(self.output_path),
            "fingerprint": self._fingerprint,
            "inputs": self._input_identities,
        }
        observed = {
            "schema_version": manifest.get("schema_version"),
            "output_path": manifest.get("output_path"),
            "fingerprint": manifest.get("fingerprint"),
            "inputs": manifest.get("inputs"),
        }
        if observed != expected:
            self._reset_root(f"Ignoring checkpoint at {self.root} because the current arguments do not match; starting fresh.")
            return

    def _reset_root(self, message: str) -> None:
        self._note(message)
        shutil.rmtree(self.root, ignore_errors=True)
        self._write_manifest()

    def _write_manifest(self) -> None:
        _write_json_atomic(
            self.manifest_path,
            {
                "schema_version": SCHEMA_VERSION,
                "output_path": str(self.output_path),
                "updated_at": _utc_now_iso(),
                "fingerprint": self._fingerprint,
                "inputs": self._input_identities,
            },
        )

    def _touch_manifest(self) -> None:
        _write_json_atomic(
            self.manifest_path,
            {
                "schema_version": SCHEMA_VERSION,
                "output_path": str(self.output_path),
                "updated_at": _utc_now_iso(),
                "fingerprint": self._fingerprint,
                "inputs": self._input_identities,
            },
        )

    def _load_item_state(self, item: InputItem) -> dict[str, Any] | None:
        state_path = self._input_dir(item) / "state.json"
        if not state_path.exists():
            return None
        return json.loads(state_path.read_text(encoding="utf-8"))

    def _write_pdf_state(
        self,
        item: InputItem,
        *,
        selected_pages: list[int] | None,
        completed_pages: list[int],
        status: str,
    ) -> None:
        payload: dict[str, Any] = {
            "source": _item_identity(item),
            "display_name": item.display_name,
            "input_type": "pdf",
            "status": status,
            "updated_at": _utc_now_iso(),
            "completed_pages": completed_pages,
        }
        if selected_pages is not None:
            payload["selected_pages"] = selected_pages
        _write_json_atomic(self._input_dir(item) / "state.json", payload)
        self._touch_manifest()

    def _load_pdf_pages(self, path: Path) -> list[PDFPageDecision]:
        if not path.exists():
            return []

        raw_content = path.read_text(encoding="utf-8")
        if not raw_content:
            return []

        raw_lines = raw_content.splitlines(keepends=True)
        ends_with_newline = raw_content.endswith("\n")
        valid_payloads: list[dict[str, Any]] = []
        truncated_tail = False
        for index, raw_line in enumerate(raw_lines):
            line = raw_line.rstrip("\n")
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except JSONDecodeError:
                is_last_line = index == len(raw_lines) - 1
                if is_last_line and not ends_with_newline:
                    truncated_tail = True
                    break
                raise
            valid_payloads.append(payload)

        if truncated_tail:
            with path.open("w", encoding="utf-8") as handle:
                for payload in valid_payloads:
                    handle.write(json.dumps(payload, ensure_ascii=False))
                    handle.write("\n")

        return [parse_pdf_page_payload(payload) for payload in valid_payloads]

    def _discard_item_checkpoint(self, item: InputItem, message: str) -> None:
        self._note(message)
        shutil.rmtree(self._input_dir(item), ignore_errors=True)

    def _note_resume(self, item: InputItem) -> None:
        key = _item_digest(item)
        if key in self._resume_noted:
            return
        self._resume_noted.add(key)
        self._note(f"Resuming from checkpoint for {item.display_name}.")

    def _input_dir(self, item: InputItem) -> Path:
        return self.root / "inputs" / _item_digest(item)

    def _note(self, message: str) -> None:
        print(message, file=sys.stderr)
