from __future__ import annotations

import io
import sys


class FakeStdout:
    def __init__(self, *, is_tty: bool):
        self.buffer = io.BytesIO()
        self._is_tty = is_tty

    def isatty(self) -> bool:
        return self._is_tty


def test_write_output_uses_utf8_for_redirected_stdout(cli_module, monkeypatch):
    fake_stdout = FakeStdout(is_tty=False)
    monkeypatch.setattr(sys, "stdout", fake_stdout)

    cli_module.write_output("dated.…", None)

    assert fake_stdout.buffer.getvalue() == "dated.…\n".encode("utf-8")


def test_write_output_uses_utf8_for_destination_file(cli_module, tmp_path):
    destination = tmp_path / "output.json"

    cli_module.write_output("dated.…", str(destination))

    assert destination.read_bytes() == "dated.…".encode("utf-8")
