from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI_EXE = ROOT / "NOSProjectsothersocrrapidocr.venv-win" / "Scripts" / "veridis-ocr-cli.exe"
RESOURCE_DIR = ROOT / "tests" / "resources"


def to_windows_path(path: Path) -> str:
    proc = subprocess.run(
        ["wslpath", "-w", str(path.resolve())],
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout.strip()


def run_cli_json(input_path: Path, *extra_args: str) -> list[dict]:
    proc = subprocess.run(
        [
            str(CLI_EXE),
            "ocr",
            to_windows_path(input_path),
            "--format",
            "json",
            *extra_args,
        ],
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stderr.decode("utf-8", errors="replace")

    stdout_text = proc.stdout.decode("utf-8")
    payload = json.loads(stdout_text)
    assert isinstance(payload, list)
    return payload


def test_constitution_resource_single_english_pass_returns_text():
    payload = run_cli_json(RESOURCE_DIR / "constituition-english.webp", "--rec-lang", "en")
    assert len(payload) == 1

    record = payload[0]
    assert record["input_type"] == "image"
    assert record["status"] == "ok"
    assert record["method_used"] == "ocr"
    assert "THE CONSTITUTION OF" in record["text"]
    assert "WE, THE PEOPLE OF INDIA" in record["text"]
    assert len(record["lines"]) >= 10


def test_tree_resource_returns_empty_text():
    payload = run_cli_json(RESOURCE_DIR / "tree.jpg", "--rec-lang", "en", "--word-boxes")
    assert len(payload) == 1

    record = payload[0]
    assert record["input_type"] == "image"
    assert record["status"] == "no_text_detected"
    assert record["method_used"] == "ocr"
    assert record["text"] == ""
    assert record["lines"] == []
    assert record["word_results"] == [[]]


def test_small_image_pdf_returns_page_records():
    payload = run_cli_json(RESOURCE_DIR / "small-image-pdf.pdf", "--rec-lang", "en")
    assert len(payload) == 1

    record = payload[0]
    assert record["input_type"] == "pdf"
    assert record["status"] == "ok"
    assert record["page_count"] == 5
    assert len(record["pages"]) == 5
    assert record["pages"][0]["method_used"] == "ocr"
    assert record["pages"][0]["status"] == "ok"
    assert "--- Page 1 ---" in record["text"]
    assert "DEED OF PARTITION" in record["text"]


def test_english_hindi_resource_returns_mixed_text():
    payload = run_cli_json(RESOURCE_DIR / "english+hindi.jpg", "--rec-lang", "en")
    assert len(payload) == 1

    record = payload[0]
    assert record["input_type"] == "image"
    assert record["status"] == "ok"
    assert record["method_used"] == "ocr"
    assert "GOVERNMENT OF MAHARASHTRA" in record["text"]
    assert "BIRTH CERTIFICATE" in record["text"]
