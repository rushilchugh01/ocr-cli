from __future__ import annotations


def test_score_native_text_quality_accepts_clean_text(cli_module):
    quality = cli_module.score_native_text_quality(
        "Invoice Total 1000\nPaid on 2026-04-14",
        {"text_coverage": 0.35, "image_coverage": 0.0},
    )

    assert quality["accepted"] is True
    assert quality["decision"] == "use_native_text"
    assert quality["score"] >= 0.75


def test_score_native_text_quality_rejects_garbled_text(cli_module):
    quality = cli_module.score_native_text_quality(
        "\ufffd\ufffd \ufffd\ufffd @@ ## \ufffd\ufffd",
        {"text_coverage": 0.01, "image_coverage": 0.85},
    )

    assert quality["accepted"] is False
    assert quality["decision"] != "use_native_text"
    assert quality["score"] < 0.55
