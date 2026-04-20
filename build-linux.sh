#!/usr/bin/env bash

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./build-linux.sh [--clean|--no-clean]

Builds a Linux one-folder PyInstaller bundle into dist-linux/veridis-ocr-cli/.
The script creates or reuses .venv-build-linux/ under the repo root.
EOF
}

CLEAN=1
case "${1-}" in
  ""|--clean)
    ;;
  --no-clean)
    CLEAN=0
    ;;
  -h|--help)
    usage
    exit 0
    ;;
  *)
    usage >&2
    exit 1
    ;;
esac

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${VENV_DIR:-$ROOT/.venv-build-linux}"
DIST_DIR="${DIST_DIR:-$ROOT/dist-linux}"
BUILD_DIR="${BUILD_DIR:-$ROOT/build-linux}"
DIST_BIN="$DIST_DIR/veridis-ocr-cli/veridis-ocr-cli"
BASE_PYTHON="${BASE_PYTHON:-python3}"

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  "$BASE_PYTHON" -m venv "$VENV_DIR"
fi

PYTHON="$VENV_DIR/bin/python"
PIP="$VENV_DIR/bin/pip"
PYINSTALLER="$VENV_DIR/bin/pyinstaller"

if (( CLEAN )); then
  rm -rf "$BUILD_DIR" "$DIST_DIR"
fi

"$PYTHON" - <<'PY'
import sys

if sys.version_info < (3, 12):
    raise SystemExit("build-linux.sh requires Python 3.12 or newer")
PY

"$PIP" install --upgrade pip
"$PIP" install pyinstaller
"$PIP" install -e "$ROOT"

MODELS_DIR="$("$PYTHON" - <<'PY'
from pathlib import Path
import rapidocr
print(Path(rapidocr.__file__).resolve().parent / "models")
PY
)"

if (( CLEAN )) && [[ -d "$MODELS_DIR" ]]; then
  find "$MODELS_DIR" -maxdepth 1 -type f -name '*.onnx' -delete
fi

"$PYTHON" "$ROOT/scripts/preload_models.py"
"$PYINSTALLER" --noconfirm --workpath "$BUILD_DIR" --distpath "$DIST_DIR" "$ROOT/rapidocr_cli.spec"

if [[ ! -x "$DIST_BIN" ]]; then
  echo "PyInstaller completed but expected artifact was not found at $DIST_BIN" >&2
  exit 1
fi

echo "Built Linux one-folder CLI at dist-linux/veridis-ocr-cli/veridis-ocr-cli"
