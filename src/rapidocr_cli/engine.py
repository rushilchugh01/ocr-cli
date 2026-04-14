from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Any

from rapidocr import LangCls, LangDet, LangRec, ModelType, OCRVersion, RapidOCR


def enum_names(enum_cls: Any) -> list[str]:
    return [item.name.lower() for item in enum_cls]


def parse_enum(value: str, enum_cls: Any, field_name: str, error_type: type[Exception]) -> Any:
    key = value.strip().replace("-", "_").upper()
    try:
        return enum_cls[key]
    except KeyError as exc:
        allowed = ", ".join(enum_names(enum_cls))
        raise error_type(f"Invalid value for {field_name}: {value}. Expected one of: {allowed}") from exc


def configure_logging(verbose: bool, log_file: str | None = None) -> None:
    logging.disable(logging.NOTSET)
    rapidocr_logger = logging.getLogger("RapidOCR")
    rapidocr_logger.disabled = False
    rapidocr_logger.setLevel(logging.INFO if verbose or log_file else logging.CRITICAL)

    for handler in list(rapidocr_logger.handlers):
        if getattr(handler, "_rapidocr_cli_handler", False):
            rapidocr_logger.removeHandler(handler)
            handler.close()

    if log_file:
        file_handler = logging.FileHandler(Path(log_file), encoding="utf-8")
        file_handler.setLevel(logging.INFO)
        setattr(file_handler, "_rapidocr_cli_handler", True)
        rapidocr_logger.addHandler(file_handler)

    if not verbose:
        return

    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.INFO)
    setattr(stream_handler, "_rapidocr_cli_handler", True)
    rapidocr_logger.addHandler(stream_handler)


def build_engine(args: argparse.Namespace, error_type: type[Exception]) -> RapidOCR:
    params = {
        "Det.lang_type": parse_enum(args.det_lang, LangDet, "--det-lang", error_type),
        "Cls.lang_type": LangCls.CH,
        "Rec.lang_type": parse_enum(args.rec_lang, LangRec, "--rec-lang", error_type),
        "Det.model_type": parse_enum(args.det_model_type, ModelType, "--det-model-type", error_type),
        "Cls.model_type": parse_enum(args.det_model_type, ModelType, "--det-model-type", error_type),
        "Rec.model_type": parse_enum(args.rec_model_type, ModelType, "--rec-model-type", error_type),
        "Det.ocr_version": parse_enum(args.det_version, OCRVersion, "--det-version", error_type),
        "Cls.ocr_version": parse_enum(args.det_version, OCRVersion, "--det-version", error_type),
        "Rec.ocr_version": parse_enum(args.rec_version, OCRVersion, "--rec-version", error_type),
    }
    return RapidOCR(params=params)


def run_ocr_for_source(engine: RapidOCR, source: str | bytes, args: argparse.Namespace) -> Any:
    return engine(
        source,
        return_word_box=args.word_boxes,
        return_single_char_box=args.single_char_boxes,
        text_score=args.text_score,
        box_thresh=args.box_thresh,
        unclip_ratio=args.unclip_ratio,
    )
