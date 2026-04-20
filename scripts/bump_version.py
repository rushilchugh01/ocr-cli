from __future__ import annotations

import argparse
import re
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYPROJECT_PATH = ROOT / "pyproject.toml"
INIT_PATH = ROOT / "src" / "rapidocr_cli" / "__init__.py"

PYPROJECT_VERSION_RE = re.compile(r'(?m)^(version = ")(\d+)\.(\d+)\.(\d+)(")$')
INIT_VERSION_RE = re.compile(r'(?m)^(__version__ = ")(\d+)\.(\d+)\.(\d+)(")$')


def parse_version(version: str) -> tuple[int, int, int]:
    parts = version.split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        raise ValueError(f"Unsupported version format: {version!r}")
    return tuple(int(part) for part in parts)


def bump_patch_version(version: str) -> str:
    major, minor, patch = parse_version(version)
    return f"{major}.{minor}.{patch + 1}"


def replace_version_in_text(text: str, pattern: re.Pattern[str], expected_version: str, new_version: str) -> str:
    match = pattern.search(text)
    if match is None:
        raise ValueError("Version field not found")
    current_version = ".".join(match.groups()[1:4])
    if current_version != expected_version:
        raise ValueError(f"Expected version {expected_version}, found {current_version}")
    return pattern.sub(rf"\g<1>{new_version}\g<5>", text, count=1)


def read_current_version() -> str:
    payload = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))
    return payload["project"]["version"]


def write_bumped_version(new_version: str) -> None:
    current_version = read_current_version()
    pyproject_text = PYPROJECT_PATH.read_text(encoding="utf-8")
    init_text = INIT_PATH.read_text(encoding="utf-8")

    PYPROJECT_PATH.write_text(
        replace_version_in_text(pyproject_text, PYPROJECT_VERSION_RE, current_version, new_version),
        encoding="utf-8",
    )
    INIT_PATH.write_text(
        replace_version_in_text(init_text, INIT_VERSION_RE, current_version, new_version),
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Patch-bump the package version in project metadata files.")
    parser.add_argument("--print-current", action="store_true", help="Print the current version and exit.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    current_version = read_current_version()
    if args.print_current:
        print(current_version)
        return 0

    new_version = bump_patch_version(current_version)
    write_bumped_version(new_version)
    print(new_version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
