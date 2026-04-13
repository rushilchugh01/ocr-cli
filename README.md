# ocr-cli

A standalone Windows CLI for OCR on images and PDFs, built on [RapidOCR](https://github.com/RapidAI/RapidOCR) with PP-OCRv5 models. Packaged as a self-contained folder with no installation required.

Supports English and Hindi (Devanagari) recognition. Outputs plain text, JSON with bounding boxes, or markdown.

---

## Download

Grab the latest `rapidocr-cli-windows-x64.zip` from the [Releases](../../releases) page. Unzip and run — no Python, no installation.

---

## Usage

```
rapidocr-cli.exe [ocr] <input> [options]
rapidocr-cli.exe check [options]
```

The `ocr` subcommand is the default. Passing an image path directly without `ocr` also works.

### OCR a single image

```powershell
.\rapidocr-cli.exe ocr .\invoice.png
```

### OCR a folder recursively, output JSON

```powershell
.\rapidocr-cli.exe ocr .\scans --recursive --format json --output .\results.json
```

### OCR with Hindi recognition

```powershell
.\rapidocr-cli.exe ocr .\document.png --rec-lang devanagari
```

### OCR with English recognition explicitly

```powershell
.\rapidocr-cli.exe ocr .\document.png --rec-lang en
```

### Save a visualization image with detected text boxes drawn

```powershell
.\rapidocr-cli.exe ocr .\document.png --save-vis .\document.vis.png
```

### Multiple inputs, save visualizations to a folder

```powershell
.\rapidocr-cli.exe ocr .\scans --recursive --save-vis .\vis-output
```

### Verify the runtime and list bundled models

```powershell
.\rapidocr-cli.exe check
.\rapidocr-cli.exe check --format json
```

---

## Options

### `ocr` command

| Flag | Default | Description |
|------|---------|-------------|
| `input` | required | Image file, directory, glob pattern, or HTTP(S) URL |
| `--format` | `text` | Output format: `text`, `json`, `markdown` |
| `--output` | stdout | Write output to a file instead of stdout |
| `--recursive` | off | Recurse into subdirectories when input is a directory |
| `--pattern` | image extensions | Glob pattern for directory input. Repeatable. |
| `--rec-lang` | `en` | Recognition language: `en`, `devanagari`, `ch` |
| `--det-lang` | `ch` | Detection language family. Only `ch` is available for PP-OCRv5. |
| `--rec-version` | `ppocrv5` | Recognizer model generation: `ppocrv5`, `ppocrv4`, `ppocrv3` |
| `--det-version` | `ppocrv5` | Detector model generation: `ppocrv5`, `ppocrv4`, `ppocrv3` |
| `--rec-model-type` | `mobile` | Recognizer model size: `mobile`, `server` |
| `--det-model-type` | `mobile` | Detector model size: `mobile`, `server` |
| `--text-score` | `0.5` | Minimum confidence threshold for recognized text lines |
| `--box-thresh` | `0.6` | Minimum confidence threshold for detected text boxes |
| `--unclip-ratio` | `1.6` | How much to expand detected boxes outward |
| `--word-boxes` | off | Include word-level boxes in JSON output |
| `--single-char-boxes` | off | Include character-level boxes in JSON output |
| `--save-vis` | off | Path to save annotated visualization image |
| `--fail-fast` | off | Stop on the first failed input |
| `--verbose` | off | Show RapidOCR runtime logs |

### `check` command

| Flag | Default | Description |
|------|---------|-------------|
| `--format` | `text` | Output format: `text`, `json` |
| `--rec-lang` | `en` | Recognition language to verify |
| `--verbose` | off | Show RapidOCR runtime logs |

---

## Output Formats

### `text` (default)

Plain extracted text. When processing multiple files, each result is separated by `>>>`.

```
To the Regional Provident Fund Commissioner,
Aurangabad/Ambattur/Thane.

Sub: Request for waiver of damages...
```

### `json`

Structured output with bounding boxes and confidence scores per line. Add `--word-boxes` for word-level detail, `--single-char-boxes` for character-level.

```json
[
  {
    "input": "C:\\docs\\letter.jpg",
    "text": "...",
    "markdown": "...",
    "lines": [
      {
        "box": [[x1,y1],[x2,y2],[x3,y3],[x4,y4]],
        "txt": "To the Regional Provident Fund Commissioner,",
        "score": 0.97681
      }
    ],
    "elapsed_seconds": 2.14
  }
]
```

Bounding boxes are four corner points (quadrilateral, not axis-aligned rectangle) in pixels from the top-left of the image.

### `markdown`

RapidOCR's built-in markdown formatter. Useful for documents with simple structure.

---

## Models

The following PP-OCRv5 mobile models are bundled in the release:

| Model | File | Purpose |
|-------|------|---------|
| CH detector | `ch_PP-OCRv5_det_mobile.onnx` | Detects text box locations. Used for all languages. |
| EN recognizer | `en_PP-OCRv5_rec_mobile.onnx` | Reads English text |
| Devanagari recognizer | `devanagari_PP-OCRv5_rec_mobile.onnx` | Reads Hindi text |

All models run on CPU via ONNX Runtime. No GPU required.

PP-OCRv5 detection is only packaged as `ch` in `rapidocr 3.8.1`. There is no separate English or Devanagari detector — the Chinese detector generalizes well across scripts.

---

## Building from Source

Requires a Windows machine with Python 3.12+.

### 1. Create a Windows venv

```powershell
python -m venv NOSProjectsothersocrrapidocr.venv-win
```

### 2. Run the build script

```powershell
.\build-exe.ps1
```

This does three things:

1. `pip install -e .` — installs the project and all dependencies into the venv
2. `python scripts/preload_models.py` — downloads PP-OCRv5 models into the venv so PyInstaller can bundle them
3. `pyinstaller rapidocr_cli.spec` — packages everything into `dist\rapidocr-cli\`

Output: `dist\rapidocr-cli\rapidocr-cli.exe`

### Skip clean (faster rebuilds)

```powershell
.\build-exe.ps1 -Clean:$false
```

By default the build script removes `build\`, `dist\`, and cached `.onnx` files before building. Pass `-Clean:$false` to skip this for faster iteration.

---

## Notes

- The build must run on Windows. PyInstaller does not cross-compile.
- Models are preloaded at build time so the exe never downloads anything at runtime.
- On first run, Windows SmartScreen may show an "unknown publisher" warning if the exe is unsigned. Click "More info" then "Run anyway" to proceed. This is a one-time prompt per downloaded file.
- The `_internal\` folder next to the exe contains the bundled DLLs and models. Do not move the exe without it.
