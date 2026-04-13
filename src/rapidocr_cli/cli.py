from __future__ import annotations

import argparse
import glob
import json
import logging
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence
from urllib.parse import urlparse

from rapidocr import LangCls, LangDet, LangRec, LoadImageError, ModelType, OCRVersion, RapidOCR

from rapidocr_cli import __version__


APP_NAME = "rapidocr-cli"
DEFAULT_PATTERNS = ["*.png", "*.jpg", "*.jpeg", "*.bmp", "*.tif", "*.tiff", "*.webp"]


class CLIError(RuntimeError):
    pass


@dataclass(frozen=True)
class InputItem:
    source: str
    display_name: str
    safe_stem: str


def enum_names(enum_cls: Any) -> list[str]:
    return [item.name.lower() for item in enum_cls]


def parse_enum(value: str, enum_cls: Any, field_name: str) -> Any:
    key = value.strip().replace("-", "_").upper()
    try:
        return enum_cls[key]
    except KeyError as exc:
        allowed = ", ".join(enum_names(enum_cls))
        raise CLIError(f"Invalid value for {field_name}: {value}. Expected one of: {allowed}") from exc


def is_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


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


def resolve_inputs(source: str, patterns: Sequence[str], recursive: bool) -> list[InputItem]:
    if is_url(source):
        return [build_input_item(source, source)]

    path = Path(source)
    if path.exists():
        if path.is_file():
            return [build_input_item(str(path), str(path.resolve()))]
        if path.is_dir():
            files = expand_directory(path, patterns, recursive)
            if not files:
                raise CLIError(f"No matching files found under directory: {path}")
            return [build_input_item(str(file_path), str(file_path.resolve())) for file_path in files]

    if any(token in source for token in ["*", "?", "["]):
        matches = dedupe_paths(Path(item) for item in glob.glob(source, recursive=recursive) if Path(item).is_file())
        if not matches:
            raise CLIError(f"No files matched glob: {source}")
        return [build_input_item(str(file_path), str(file_path.resolve())) for file_path in matches]

    raise CLIError(f"Input not found: {source}")


def configure_logging(verbose: bool) -> None:
    logging.disable(logging.NOTSET if verbose else logging.CRITICAL)
    logging.getLogger("RapidOCR").disabled = not verbose
    logging.getLogger("RapidOCR").setLevel(logging.INFO if verbose else logging.CRITICAL)


def build_engine(args: argparse.Namespace) -> RapidOCR:
    params = {
        "Det.lang_type": parse_enum(args.det_lang, LangDet, "--det-lang"),
        "Cls.lang_type": LangCls.CH,
        "Rec.lang_type": parse_enum(args.rec_lang, LangRec, "--rec-lang"),
        "Det.model_type": parse_enum(args.det_model_type, ModelType, "--det-model-type"),
        "Cls.model_type": parse_enum(args.det_model_type, ModelType, "--det-model-type"),
        "Rec.model_type": parse_enum(args.rec_model_type, ModelType, "--rec-model-type"),
        "Det.ocr_version": parse_enum(args.det_version, OCRVersion, "--det-version"),
        "Cls.ocr_version": parse_enum(args.det_version, OCRVersion, "--det-version"),
        "Rec.ocr_version": parse_enum(args.rec_version, OCRVersion, "--rec-version"),
    }
    return RapidOCR(params=params)


def to_float_list(points: Any) -> list[list[float]]:
    return [[float(x), float(y)] for x, y in points]


def serialize_word_results(word_results: Any) -> list[list[dict[str, Any]]]:
    serialized: list[list[dict[str, Any]]] = []
    for line in word_results or ():
        line_items: list[dict[str, Any]] = []
        for item in line:
            text, score, box = item
            line_items.append(
                {
                    "txt": str(text),
                    "score": float(score),
                    "box": to_float_list(box),
                }
            )
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
        candidate.mkdir(parents=True, exist_ok=True)
        return candidate / f"{item.safe_stem}.vis.png"

    if candidate.suffix:
        candidate.parent.mkdir(parents=True, exist_ok=True)
        return candidate

    candidate.mkdir(parents=True, exist_ok=True)
    return candidate / f"{item.safe_stem}.vis.png"


def render_output(records: list[dict[str, Any]], output_format: str) -> str:
    if output_format == "json":
        return json.dumps(records, ensure_ascii=False, indent=2)

    if output_format == "markdown":
        if len(records) == 1:
            return records[0]["markdown"]
        chunks = []
        for record in records:
            chunks.append(f"## {record['input']}\n\n{record['markdown']}".rstrip())
        return "\n\n".join(chunks).strip()

    if len(records) == 1:
        return records[0]["text"]

    chunks = []
    for record in records:
        chunks.append(f">>> {record['input']}\n{record['text']}".rstrip())
    return "\n\n".join(chunks).strip()


def write_output(content: str, destination: str | None) -> None:
    if destination:
        path = Path(destination)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return
    try:
        print(content)
    except UnicodeEncodeError:
        # Fall back to replacement characters instead of crashing on Windows
        # consoles that are not configured for UTF-8.
        sys.stdout.buffer.write(content.encode(sys.stdout.encoding or "utf-8", errors="replace"))
        sys.stdout.buffer.write(b"\n")


def build_record(item: InputItem, result: Any, visualization_path: Path | None) -> dict[str, Any]:
    lines = result.to_json() or []
    text = "\n".join(line["txt"] for line in lines)
    record: dict[str, Any] = {
        "input": item.display_name,
        "text": text,
        "markdown": result.to_markdown(),
        "lines": lines,
        "elapsed_seconds": float(result.elapse),
        "visualization_path": str(visualization_path.resolve()) if visualization_path else None,
    }
    if result.word_results:
        record["word_results"] = serialize_word_results(result.word_results)
    return record


def run_check(args: argparse.Namespace) -> int:
    configure_logging(args.verbose)
    engine = build_engine(args)

    import rapidocr

    models_dir = Path(rapidocr.__file__).resolve().parent / "models"
    payload = {
        "status": "ok",
        "version": __version__,
        "python": sys.version.split()[0],
        "models_dir": str(models_dir),
        "models": sorted(path.name for path in models_dir.glob("*.onnx")),
        "det_lang": args.det_lang,
        "rec_lang": args.rec_lang,
        "det_model_type": args.det_model_type,
        "rec_model_type": args.rec_model_type,
        "det_version": args.det_version,
        "rec_version": args.rec_version,
        "engine_ready": isinstance(engine, RapidOCR),
    }
    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("RapidOCR runtime is ready.")
        print(f"Models: {len(payload['models'])} in {payload['models_dir']}")
    return 0


def run_ocr(args: argparse.Namespace) -> int:
    configure_logging(args.verbose)
    engine = build_engine(args)
    inputs = resolve_inputs(args.input, args.pattern, args.recursive)
    multiple_inputs = len(inputs) > 1

    records: list[dict[str, Any]] = []
    failures: list[str] = []

    for item in inputs:
        try:
            result = engine(
                item.source,
                return_word_box=args.word_boxes,
                return_single_char_box=args.single_char_boxes,
                text_score=args.text_score,
                box_thresh=args.box_thresh,
                unclip_ratio=args.unclip_ratio,
            )
        except LoadImageError as exc:
            message = f"{item.display_name}: {exc}"
            if args.fail_fast:
                raise CLIError(message) from exc
            failures.append(message)
            continue
        except Exception as exc:
            message = f"{item.display_name}: {exc}"
            if args.fail_fast:
                raise CLIError(message) from exc
            failures.append(message)
            continue

        visualization_path = choose_visualization_path(args.save_vis, item, multiple_inputs)
        if visualization_path is not None:
            result.vis(str(visualization_path))
        records.append(build_record(item, result, visualization_path))

    if not records and failures:
        for failure in failures:
            print(f"ERROR: {failure}", file=sys.stderr)
        return 2

    content = render_output(records, args.format)
    write_output(content, args.output)

    if failures:
        for failure in failures:
            print(f"ERROR: {failure}", file=sys.stderr)
        return 2
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=APP_NAME, description="OCR images and URLs with RapidOCR.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    subparsers = parser.add_subparsers(dest="command")

    ocr_parser = subparsers.add_parser("ocr", help="Run OCR on one input, a glob, or a directory.")
    ocr_parser.add_argument("input", help="Image path, directory, glob, or HTTP(S) URL.")
    ocr_parser.add_argument(
        "--pattern",
        action="append",
        default=[],
        help="Glob pattern for directory input. Repeatable. Defaults to common image extensions.",
    )
    ocr_parser.add_argument("--recursive", action="store_true", help="Recurse when the input is a directory or glob.")
    ocr_parser.add_argument("--format", choices=["text", "json", "markdown"], default="text", help="Output format.")
    ocr_parser.add_argument("--output", help="Write OCR output to a file instead of stdout.")
    ocr_parser.add_argument(
        "--save-vis",
        help="Save annotated visualization. Use a file path for one input or a directory for multiple inputs.",
    )
    ocr_parser.add_argument("--word-boxes", action="store_true", help="Include word-level OCR details in JSON output.")
    ocr_parser.add_argument(
        "--single-char-boxes",
        action="store_true",
        help="Include character-level OCR details inside the JSON word_results payload.",
    )
    ocr_parser.add_argument("--text-score", type=float, help="Override the text confidence threshold.")
    ocr_parser.add_argument("--box-thresh", type=float, help="Override the detector box threshold.")
    ocr_parser.add_argument("--unclip-ratio", type=float, help="Override the detector unclip ratio.")
    ocr_parser.add_argument("--det-lang", choices=enum_names(LangDet), default="ch", help="Detection language family.")
    ocr_parser.add_argument("--rec-lang", choices=enum_names(LangRec), default="en", help="Recognition language.")
    ocr_parser.add_argument(
        "--det-model-type",
        choices=enum_names(ModelType),
        default="mobile",
        help="Detector model size.",
    )
    ocr_parser.add_argument(
        "--rec-model-type",
        choices=enum_names(ModelType),
        default="mobile",
        help="Recognizer model size.",
    )
    ocr_parser.add_argument(
        "--det-version",
        choices=enum_names(OCRVersion),
        default="ppocrv5",
        help="Detector model generation.",
    )
    ocr_parser.add_argument(
        "--rec-version",
        choices=enum_names(OCRVersion),
        default="ppocrv5",
        help="Recognizer model generation.",
    )
    ocr_parser.add_argument("--fail-fast", action="store_true", help="Stop on the first failed input.")
    ocr_parser.add_argument("--verbose", action="store_true", help="Show RapidOCR runtime logs.")

    check_parser = subparsers.add_parser("check", help="Verify that the OCR runtime and bundled models are ready.")
    check_parser.add_argument("--format", choices=["text", "json"], default="text", help="Output format.")
    check_parser.add_argument("--det-lang", choices=enum_names(LangDet), default="ch", help="Detection language family.")
    check_parser.add_argument("--rec-lang", choices=enum_names(LangRec), default="en", help="Recognition language.")
    check_parser.add_argument(
        "--det-model-type",
        choices=enum_names(ModelType),
        default="mobile",
        help="Detector model size.",
    )
    check_parser.add_argument(
        "--rec-model-type",
        choices=enum_names(ModelType),
        default="mobile",
        help="Recognizer model size.",
    )
    check_parser.add_argument(
        "--det-version",
        choices=enum_names(OCRVersion),
        default="ppocrv5",
        help="Detector model generation.",
    )
    check_parser.add_argument(
        "--rec-version",
        choices=enum_names(OCRVersion),
        default="ppocrv5",
        help="Recognizer model generation.",
    )
    check_parser.add_argument("--verbose", action="store_true", help="Show RapidOCR runtime logs.")

    return parser


def normalize_argv(argv: Sequence[str]) -> list[str]:
    if not argv:
        return list(argv)
    if argv[0] in {"ocr", "check", "-h", "--help", "--version"}:
        return list(argv)
    return ["ocr", *argv]


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    normalized_argv = normalize_argv(list(argv) if argv is not None else sys.argv[1:])
    args = parser.parse_args(normalized_argv)

    if args.command == "check":
        try:
            return run_check(args)
        except CLIError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2

    if args.command == "ocr":
        if not args.pattern:
            args.pattern = DEFAULT_PATTERNS
        try:
            return run_ocr(args)
        except CLIError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
