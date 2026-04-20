#!/usr/bin/env bash

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./build-macos.sh [--clean|--no-clean]

Builds an Apple Silicon macOS one-folder PyInstaller bundle into
dist-macos/veridis-ocr-cli/.
The script creates or reuses .venv-build-macos/ under the repo root.
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
VENV_DIR="${VENV_DIR:-$ROOT/.venv-build-macos}"
DIST_DIR="${DIST_DIR:-$ROOT/dist-macos}"
BUILD_DIR="${BUILD_DIR:-$ROOT/build-macos}"
DIST_BIN="$DIST_DIR/veridis-ocr-cli/veridis-ocr-cli"
BASE_PYTHON="${BASE_PYTHON:-python3}"

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  "$BASE_PYTHON" -m venv "$VENV_DIR"
fi

PYTHON="$VENV_DIR/bin/python"

if (( CLEAN )); then
  rm -rf "$BUILD_DIR" "$DIST_DIR"
fi

"$PYTHON" - <<'PY'
import platform
import sys

if sys.version_info < (3, 12):
    raise SystemExit("build-macos.sh requires Python 3.12 or newer")
if platform.system() != "Darwin":
    raise SystemExit("build-macos.sh must be run on macOS")
if platform.machine() != "arm64":
    raise SystemExit("build-macos.sh only supports Apple Silicon (arm64)")
PY

"$PYTHON" -m pip install --upgrade pip
"$PYTHON" -m pip install pyinstaller
"$PYTHON" -m pip install -e "$ROOT"

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
"$PYTHON" -m PyInstaller --noconfirm --workpath "$BUILD_DIR" --distpath "$DIST_DIR" "$ROOT/rapidocr_cli.spec"

if [[ ! -x "$DIST_BIN" ]]; then
  echo "PyInstaller completed but expected artifact was not found at $DIST_BIN" >&2
  exit 1
fi

echo "Built macOS arm64 one-folder CLI at dist-macos/veridis-ocr-cli/veridis-ocr-cli"
