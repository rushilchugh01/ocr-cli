import pytest

def test_build_record_skips_empty_word_results(cli_module):
    item = cli_module.InputItem(
        source="C:/Users/rushi/Downloads/images.jpg",
        display_name="C:/Users/rushi/Downloads/images.jpg",
        safe_stem="images",
    )

    class FakeResult:
        elapse = 0.123
        word_results = [[(), ("tree", 0.98, ((1, 2), (3, 4)))], []]

        @staticmethod
        def to_json():
            return []

        @staticmethod
        def to_markdown():
            return ""

    record = cli_module.build_record(item, FakeResult(), None)

    assert record["input"] == item.display_name
    assert record["text"] == ""
    assert record["lines"] == []
    assert record["elapsed_seconds"] == pytest.approx(0.123)
    assert record["visualization_path"] is None
    assert record["word_results"] == [[{"txt": "tree", "score": 0.98, "box": [[1.0, 2.0], [3.0, 4.0]]}], []]
