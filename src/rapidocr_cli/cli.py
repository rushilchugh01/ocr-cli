from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from rapidocr import LangCls, LangDet, LangRec, LoadImageError, ModelType, OCRVersion, RapidOCR

from rapidocr_cli import __version__
from rapidocr_cli.engine import build_engine, configure_logging, enum_names, run_ocr_for_source
from rapidocr_cli.inputs import (
    InputItem,
    build_input_item,
    dedupe_paths,
    expand_directory,
    is_pdf_source,
    is_url,
    resolve_inputs,
    sanitize_name,
)
from rapidocr_cli.output import (
    OutputSession,
    build_record,
    build_pdf_page_record,
    build_pdf_record,
    choose_pdf_visualization_path,
    choose_visualization_path,
    is_word_result_item,
    render_output,
    render_pdf_markdown,
    render_pdf_text,
    serialize_word_results,
    to_float_list,
    write_output,
)
from rapidocr_cli.pdf import (
    iter_pdf_page_records as iter_pdf_page_records_impl,
    is_pdf_runtime_ready as is_pdf_runtime_ready_impl,
    load_pdf_module as load_pdf_module_impl,
    parse_page_spec as parse_page_spec_impl,
    process_pdf_input as process_pdf_input_impl,
    rasterize_pdf_page as rasterize_pdf_page_impl,
)
from rapidocr_cli.pdf_quality import (
    bbox_area,
    compute_pdf_layout_metrics,
    normalize_text,
    ratio,
    score_native_text_quality,
)


APP_NAME = "veridis-ocr-cli"
DEFAULT_PATTERNS = ["*.png", "*.jpg", "*.jpeg", "*.bmp", "*.tif", "*.tiff", "*.webp", "*.pdf"]


class CLIError(RuntimeError):
    pass


def parse_page_spec(page_spec: str | None, page_count: int) -> list[int]:
    return parse_page_spec_impl(page_spec, page_count, CLIError)


def load_pdf_module() -> Any:
    return load_pdf_module_impl(CLIError)


def is_pdf_runtime_ready() -> bool:
    return is_pdf_runtime_ready_impl(CLIError)


def rasterize_pdf_page(page: Any, dpi: int) -> bytes:
    return rasterize_pdf_page_impl(page, dpi, CLIError)


def process_pdf_input(
    item: InputItem,
    engine: RapidOCR,
    args: argparse.Namespace,
    multiple_inputs: bool,
) -> dict[str, Any]:
    return process_pdf_input_impl(item, engine, args, multiple_inputs, CLIError)


def iter_pdf_page_records(
    item: InputItem,
    engine: RapidOCR,
    args: argparse.Namespace,
    multiple_inputs: bool,
):
    return iter_pdf_page_records_impl(item, engine, args, multiple_inputs, CLIError)


def run_check(args: argparse.Namespace) -> int:
    configure_logging(args.verbose, getattr(args, "log_file", None))
    engine = build_engine(args, CLIError)

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
        "pdf_runtime_ready": is_pdf_runtime_ready(),
    }
    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("RapidOCR runtime is ready.")
        print(f"Models: {len(payload['models'])} in {payload['models_dir']}")
    return 0


def emit_no_text_notice(record: dict[str, Any], output_format: str) -> None:
    if output_format == "json":
        return
    if record.get("status") != "no_text_detected":
        return
    print(f"No valid text detected: {record['input']}", file=sys.stderr)


def run_ocr(args: argparse.Namespace) -> int:
    configure_logging(args.verbose, getattr(args, "log_file", None))
    engine = build_engine(args, CLIError)
    inputs = resolve_inputs(args.input, args.pattern, args.recursive, CLIError)
    multiple_inputs = len(inputs) > 1

    failures: list[str] = []
    success_count = 0
    session = OutputSession(args.format, args.output, multiple_inputs)

    try:
        for item in inputs:
            try:
                if is_pdf_source(item.source):
                    record = session.add_pdf_record(item, iter_pdf_page_records(item, engine, args, multiple_inputs))
                else:
                    result = run_ocr_for_source(engine, item.source, args)
                    visualization_path = choose_visualization_path(args.save_vis, item, multiple_inputs)
                    if visualization_path is not None:
                        result.vis(str(visualization_path))
                    record = build_record(item, result, visualization_path)
                    session.add_record(record)
                emit_no_text_notice(record, args.format)
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
            success_count += 1
    except Exception:
        session.finalize(commit=False)
        raise

    if not success_count and failures:
        session.finalize(commit=False)
        for failure in failures:
            print(f"ERROR: {failure}", file=sys.stderr)
        return 2

    session.finalize(commit=True)

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
    ocr_parser.add_argument(
        "--rec-lang",
        choices=enum_names(LangRec),
        default="devanagari",
        help="Recognition language.",
    )
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
    ocr_parser.add_argument("--log-file", help="Write runtime logs to a UTF-8 log file.")
    ocr_parser.add_argument("--pages", help="PDF pages to process, e.g. 1,3,5-7. Applies only to PDF input.")
    ocr_parser.add_argument(
        "--pdf-mode",
        choices=["auto", "text", "ocr"],
        default="auto",
        help="PDF extraction mode: native text first (`auto`), text-only (`text`), or OCR every page (`ocr`).",
    )
    ocr_parser.add_argument(
        "--pdf-dpi",
        type=int,
        default=144,
        help="Rasterization DPI for PDF pages that need OCR.",
    )
    ocr_parser.add_argument("--verbose", action="store_true", help="Show RapidOCR runtime logs.")

    check_parser = subparsers.add_parser("check", help="Verify that the OCR runtime and bundled models are ready.")
    check_parser.add_argument("--format", choices=["text", "json"], default="text", help="Output format.")
    check_parser.add_argument("--det-lang", choices=enum_names(LangDet), default="ch", help="Detection language family.")
    check_parser.add_argument(
        "--rec-lang",
        choices=enum_names(LangRec),
        default="devanagari",
        help="Recognition language.",
    )
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
    check_parser.add_argument("--log-file", help="Write runtime logs to a UTF-8 log file.")
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
