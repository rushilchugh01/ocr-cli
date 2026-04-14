from __future__ import annotations

import csv
import importlib.util
import subprocess
import sys
import time
import types
from enum import Enum
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src" / "rapidocr_cli"


def make_fake_rapidocr_module() -> types.ModuleType:
    module = types.ModuleType("rapidocr")

    class LangCls(Enum):
        CH = "ch"

    class LangDet(Enum):
        CH = "ch"

    class LangRec(Enum):
        EN = "en"
        DEVANAGARI = "devanagari"

    class LoadImageError(Exception):
        pass

    class ModelType(Enum):
        MOBILE = "mobile"

    class OCRVersion(Enum):
        PPOCRV5 = "ppocrv5"

    class RapidOCR:
        pass

    module.LangCls = LangCls
    module.LangDet = LangDet
    module.LangRec = LangRec
    module.LoadImageError = LoadImageError
    module.ModelType = ModelType
    module.OCRVersion = OCRVersion
    module.RapidOCR = RapidOCR
    return module


@pytest.fixture()
def cli_module(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setitem(sys.modules, "rapidocr", make_fake_rapidocr_module())

    package_spec = importlib.util.spec_from_file_location(
        "rapidocr_cli",
        SRC_DIR / "__init__.py",
        submodule_search_locations=[str(SRC_DIR)],
    )
    assert package_spec is not None and package_spec.loader is not None
    package_module = importlib.util.module_from_spec(package_spec)
    monkeypatch.setitem(sys.modules, "rapidocr_cli", package_module)
    package_spec.loader.exec_module(package_module)

    cli_spec = importlib.util.spec_from_file_location("rapidocr_cli.cli", SRC_DIR / "cli.py")
    assert cli_spec is not None and cli_spec.loader is not None
    cli_module = importlib.util.module_from_spec(cli_spec)
    monkeypatch.setitem(sys.modules, "rapidocr_cli.cli", cli_module)
    cli_spec.loader.exec_module(cli_module)
    return cli_module


# ---------------------------------------------------------------------------
# Timing: record elapsed seconds for every test into tests/results/<commit>.csv
# ---------------------------------------------------------------------------

RESULTS_DIR = ROOT / "tests" / "results"

_FIELDS = ["commit", "test_id", "outcome", "elapsed_s"]


def _get_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=ROOT,
        )
        return result.stdout.strip()
    except Exception:
        return "unknown"


@pytest.fixture(autouse=True)
def _record_timing(request: pytest.FixtureRequest) -> pytest.Generator[None, None, None]:
    start = time.perf_counter()
    yield
    elapsed = time.perf_counter() - start

    outcome = "passed"
    rep = getattr(request.node, "rep_call", None)
    if rep is not None:
        if rep.failed:
            outcome = "failed"
        elif rep.skipped:
            outcome = "skipped"

    commit = _get_commit()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = RESULTS_DIR / f"{commit}.csv"
    write_header = not csv_path.exists()

    with csv_path.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=_FIELDS)
        if write_header:
            writer.writeheader()
        writer.writerow({
            "commit": commit,
            "test_id": request.node.nodeid,
            "outcome": outcome,
            "elapsed_s": f"{elapsed:.4f}",
        })


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo) -> pytest.Generator[None, None, None]:
    outcome = yield
    rep = outcome.get_result()
    setattr(item, f"rep_{rep.when}", rep)
