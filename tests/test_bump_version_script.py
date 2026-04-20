from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "bump_version.py"


def load_module():
    spec = importlib.util.spec_from_file_location("bump_version", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_bump_patch_version() -> None:
    module = load_module()
    assert module.bump_patch_version("0.1.2") == "0.1.3"


def test_replace_version_in_text() -> None:
    module = load_module()
    text = 'version = "0.1.2"\nname = "veridis-ocr-cli"\n'
    updated = module.replace_version_in_text(text, module.PYPROJECT_VERSION_RE, "0.1.2", "0.1.3")
    assert updated == 'version = "0.1.3"\nname = "veridis-ocr-cli"\n'
