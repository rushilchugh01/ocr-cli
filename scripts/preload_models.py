from rapidocr import LangCls, LangDet, LangRec, ModelType, OCRVersion, RapidOCR


def preload(params):
    RapidOCR(params=params)


def main() -> None:
    # PP-OCRv5 detection is only available as `ch` in rapidocr 3.8.1.
    # Preload English and Devanagari recognizers so the packaged exe can
    # switch between them without downloading models at runtime.
    common_v5 = {
        "Det.lang_type": LangDet.CH,
        "Det.model_type": ModelType.MOBILE,
        "Det.ocr_version": OCRVersion.PPOCRV5,
        "Cls.lang_type": LangCls.CH,
        "Cls.model_type": ModelType.MOBILE,
        "Cls.ocr_version": OCRVersion.PPOCRV5,
        "Rec.model_type": ModelType.MOBILE,
        "Rec.ocr_version": OCRVersion.PPOCRV5,
    }

    preload(
        {
            **common_v5,
            "Rec.lang_type": LangRec.EN,
        }
    )
    preload(
        {
            **common_v5,
            "Rec.lang_type": LangRec.DEVANAGARI,
        }
    )


if __name__ == "__main__":
    main()
