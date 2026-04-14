from __future__ import annotations

import glob
import re
from pathlib import Path
from typing import Iterable, Sequence
from urllib.parse import urlparse

from rapidocr_cli.types import InputItem


def is_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def is_pdf_source(value: str) -> bool:
    if is_url(value):
        return Path(urlparse(value).path).suffix.lower() == ".pdf"
    return Path(value).suffix.lower() == ".pdf"


def sanitize_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return cleaned.strip("._") or "ocr_input"


def build_input_item(source: str, display_name: str) -> InputItem:
    if is_url(source):
        parsed = urlparse(source)
        base = Path(parsed.path).stem or parsed.netloc or "url_input"
    else:
        base = Path(display_name).stem or "ocr_input"
    return InputItem(source=source, display_name=display_name, safe_stem=sanitize_name(base))


def dedupe_paths(paths: Iterable[Path]) -> list[Path]:
    seen: set[str] = set()
    unique: list[Path] = []
    for path in paths:
        resolved = str(path.resolve())
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(path)
    return sorted(unique, key=lambda item: str(item).lower())


def expand_directory(path: Path, patterns: Sequence[str], recursive: bool) -> list[Path]:
    files: list[Path] = []
    for pattern in patterns:
        iterator = path.rglob(pattern) if recursive else path.glob(pattern)
        files.extend(candidate for candidate in iterator if candidate.is_file())
    return dedupe_paths(files)


def resolve_inputs(
    source: str,
    patterns: Sequence[str],
    recursive: bool,
    error_type: type[Exception],
) -> list[InputItem]:
    if is_url(source):
        return [build_input_item(source, source)]

    path = Path(source)
    if path.exists():
        if path.is_file():
            return [build_input_item(str(path), str(path.resolve()))]
        if path.is_dir():
            files = expand_directory(path, patterns, recursive)
            if not files:
                raise error_type(f"No matching files found under directory: {path}")
            return [build_input_item(str(file_path), str(file_path.resolve())) for file_path in files]

    if any(token in source for token in ["*", "?", "["]):
        matches = dedupe_paths(Path(item) for item in glob.glob(source, recursive=recursive) if Path(item).is_file())
        if not matches:
            raise error_type(f"No files matched glob: {source}")
        return [build_input_item(str(file_path), str(file_path.resolve())) for file_path in matches]

    raise error_type(f"Input not found: {source}")
