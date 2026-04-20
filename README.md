# veridis-ocr-cli

A standalone CLI for OCR on images and PDFs, built on [RapidOCR](https://github.com/RapidAI/RapidOCR) with PP-OCRv5 models. Packaged as self-contained binaries for Windows, Linux, and Apple Silicon macOS, with best-effort automatic resume for interrupted runs when `--output` is used.

Supports English and Hindi (Devanagari) recognition. Outputs plain text, JSON with bounding boxes, or markdown.

---

## Download

Grab the latest release for your platform from the [Releases](../../releases) page:

- **Windows x64**: `veridis-ocr-cli-windows-x64-v*.zip`
- **Linux x64**: `veridis-ocr-cli-linux-x64-v*.tar.gz`
- **macOS arm64**: `veridis-ocr-cli-macos-arm64-v*.tar.gz`

Unzip/untar and run — no Python or installation required.

## Platform Support

- **Windows x64**: published release artifact, built in GitHub Actions, smoke-tested with `--version` and `check`
- **Linux x64**: published release artifact, built in GitHub Actions, smoke-tested with `--version` and `check`
- **macOS arm64 (Apple Silicon)**: published release artifact, built on the `macos-15` GitHub-hosted arm64 runner, smoke-tested with `--version` and `check`
- **macOS Intel**: not currently built or published

---

## Usage

```bash
veridis-ocr-cli [ocr] <input> [options]
veridis-ocr-cli check [options]
```

The `ocr` subcommand is the default. Passing an image path directly without `ocr` also works.

### OCR a single image

```bash
./veridis-ocr-cli ocr ./invoice.png
```

### OCR a folder recursively, output JSON

```bash
./veridis-ocr-cli ocr ./scans --recursive --format json --output ./results.json
```

### Resume an interrupted PDF run automatically

```bash
./veridis-ocr-cli ocr ./bundle.pdf --format json --output ./bundle.json
```

If the process is killed or crashes, rerun the same command. When the prior checkpoint is still valid, the CLI resumes automatically instead of starting from page 1 again.

### OCR selected PDF pages only

```bash
./veridis-ocr-cli ocr ./bundle.pdf --pages 1,3,5-7
```

### Use native PDF text first and OCR only fallback pages

```bash
./veridis-ocr-cli ocr ./bundle.pdf --pdf-mode auto
```

### Force OCR on every selected PDF page

```bash
./veridis-ocr-cli ocr ./bundle.pdf --pdf-mode ocr --pdf-dpi 200
```

### Capture OCR and PDF routing logs to a file

```bash
./veridis-ocr-cli ocr ./bundle.pdf --log-file ./veridis-ocr-debug.log
```

### OCR with Hindi recognition

```bash
./veridis-ocr-cli ocr ./document.png --rec-lang devanagari
```

### OCR with English recognition explicitly

```bash
./veridis-ocr-cli ocr ./document.png --rec-lang en
```

### Save a visualization image with detected text boxes drawn

```bash
./veridis-ocr-cli ocr ./document.png --save-vis ./document.vis.png
```

### Multiple inputs, save visualizations to a folder

```bash
./veridis-ocr-cli ocr ./scans --recursive --save-vis ./vis-output
```

### Verify the runtime and list bundled models

```bash
./veridis-ocr-cli check
./veridis-ocr-cli check --format json
```

---

## Options

### `ocr` command

| Flag | Default | Description |
|------|---------|-------------|
| `input` | required | Image file, directory, glob pattern, or HTTP(S) URL |
| `--format` | `text` | Output format: `text`, `json`, `markdown` |
| `--output` | stdout | Write output to a file instead of stdout. Also enables automatic checkpointed resume for interrupted runs. |
| `--recursive` | off | Recurse into subdirectories when input is a directory |
| `--pattern` | image extensions | Glob pattern for directory input. Repeatable. |
| `--rec-lang` | `devanagari` | Recognition language: `en`, `devanagari`, `ch` |
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
| `--log-file` | off | Write CLI and RapidOCR logs to a UTF-8 log file |
| `--pages` | all pages | PDF pages to process, e.g. `1,3,5-7` |
| `--pdf-mode` | `auto` | PDF mode: `auto`, `text`, `ocr` |
| `--pdf-dpi` | `144` | Rasterization DPI for PDF pages that need OCR |
| `--fail-fast` | off | Stop on the first failed input |
| `--verbose` | off | Show RapidOCR runtime logs |

### `check` command

| Flag | Default | Description |
|------|---------|-------------|
| `--format` | `text` | Output format: `text`, `json` |
| `--log-file` | off | Write CLI and RapidOCR logs to a UTF-8 log file |
| `--rec-lang` | `devanagari` | Recognition language to verify |
| `--verbose` | off | Show RapidOCR runtime logs |

---

## Resume And Checkpoints

Automatic resume is best-effort and is designed mainly for long PDFs.

- Resume activates only when `--output` is set, because the run then has a stable identity.
- Checkpoints are stored under an app-owned deterministic directory in the OS temp area, not next to the output file.
- If a recent matching checkpoint exists, rerunning the same command resumes automatically.
- If the checkpoint is stale, incompatible with the new command, missing, or corrupt, the CLI logs a short note and starts fresh.
- Successful runs remove the checkpoint. Failed or killed runs leave it behind for the next retry.

Current policy:

- Checkpoints older than 48 hours are treated as stale and ignored.
- Partial PDF progress is restored from page-level checkpoint data.
- Completed image inputs are skipped on retry when their checkpoint record is still valid.

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

Every OCR record includes a small status contract:

- `status`: `ok`, `no_text_detected`, or `error`
- `reason`: machine-readable detail such as `no_valid_text_detected`
- `message`: short human-readable English message or `null`

For image records:

- `status: "ok"` means OCR returned usable text
- `status: "no_text_detected"` means OCR ran successfully but returned no usable text
- `text`, `markdown`, and `lines` stay empty for `no_text_detected`

For PDF input, JSON keeps one top-level file record and adds `pages[]` with per-page `page_number`, `status`, `reason`, `message`, `method_used`, `native_text_score`, `decision`, `fallback_reason`, `text`, and OCR details when OCR was used. PDF file records also include:

- `page_count`
- `pages_with_text`
- `no_text_pages`

If every selected page is empty, the top-level PDF record uses `status: "no_text_detected"` with `reason: "no_valid_text_detected"`.

### `markdown`

RapidOCR's built-in markdown formatter. Useful for documents with simple structure.

If no usable text is found, `text` and `markdown` output stay empty. The CLI prints a short notice to `stderr` such as `No valid text detected: tree.jpg` instead of injecting that message into the extracted content.

---

## Input/Output Contract

### Inputs

The `ocr` command accepts:

| Input type | Example |
|------------|---------|
| Single image file | `./invoice.png` |
| PDF file | `./bundle.pdf` |
| HTTP(S) URL | `https://example.com/scan.jpg` |
| Directory | `./scans/` (walks matching files) |
| Glob pattern | `./docs/**/*.png` |

Supported image extensions (default `--pattern`): `.png`, `.jpg`, `.jpeg`, `.bmp`, `.tif`, `.tiff`, `.webp`, `.pdf`

### JSON output — image record

```json
{
  "input": "invoice.png",
  "input_type": "image",
  "status": "ok",
  "reason": null,
  "message": null,
  "method_used": "ocr",
  "text": "extracted plain text",
  "markdown": "extracted markdown",
  "lines": [
    {
      "box": [[x1,y1],[x2,y2],[x3,y3],[x4,y4]],
      "txt": "line text",
      "score": 0.977
    }
  ],
  "elapsed_seconds": 1.23,
  "visualization_path": null
}
```

`word_results` (array of arrays) is included only when `--word-boxes` is passed:

```json
"word_results": [
  [
    { "txt": "word", "score": 0.98, "box": [[x1,y1],[x2,y2],[x3,y3],[x4,y4]] }
  ]
]
```

### JSON output — PDF record

```json
{
  "input": "bundle.pdf",
  "input_type": "pdf",
  "status": "ok",
  "reason": null,
  "message": null,
  "page_count": 5,
  "pages_with_text": 4,
  "no_text_pages": 1,
  "text": "--- Page 1 ---\n...\n\n--- Page 2 ---\n...",
  "markdown": "## Page 1\n\n...\n\n## Page 2\n\n...",
  "lines": [],
  "elapsed_seconds": 8.45,
  "visualization_path": null,
  "pages": [...]
}
```

Each entry in `pages` is a per-page record:

```json
{
  "page_number": 1,
  "status": "ok",
  "reason": null,
  "message": null,
  "method_used": "native_text",
  "text": "page text",
  "markdown": "page markdown",
  "lines": [],
  "elapsed_seconds": 0.12,
  "native_text_found": true,
  "native_text_accepted": true,
  "native_text_score": 0.91,
  "decision": "use_native",
  "fallback_reason": null,
  "quality_metrics": { ... },
  "visualization_path": null
}
```

`method_used` is `"native_text"` when the PDF's embedded text was used, `"ocr"` when the page was rasterized and OCR'd.

`decision` values: `"use_native"`, `"fallback_to_ocr"`.

`fallback_reason` is `null` unless OCR fallback was triggered, in which case it explains why native text was rejected (e.g. `"low_quality_score"`).

### Status contract (all record types)

| Field | Type | Meaning |
|-------|------|---------|
| `status` | `"ok"` \| `"no_text_detected"` | Whether usable text was extracted |
| `reason` | `string` \| `null` | Machine-readable detail; `"no_valid_text_detected"` when status is not ok |
| `message` | `string` \| `null` | Short human-readable English message or `null` |

`text`, `markdown`, and `lines` are always present but empty when `status` is `"no_text_detected"`. The CLI never injects status messages into these fields.

### Exit codes

| Code | Meaning |
|------|---------|
| `0` | All inputs succeeded |
| `1` | Bad arguments / no subcommand |
| `2` | One or more inputs failed (partial results may still be written) |

---

## Models

The following PP-OCRv5 mobile models are bundled in the release:

| Model | File | Purpose |
|-------|------|---------|
| CH detector | `ch_PP-OCRv5_det_mobile.onnx` | Detects text box locations. Used for all languages. |
| EN recognizer | `en_PP-OCRv5_rec_mobile.onnx` | Reads English text |
| Devanagari recognizer | `devanagari_PP-OCRv5_rec_mobile.onnx` | Reads Hindi text |

All models run on CPU via ONNX Runtime. No GPU required.

PDF handling uses PyMuPDF for page parsing, native text extraction, and rasterization of OCR fallback pages.

PP-OCRv5 detection is only packaged as `ch` in `rapidocr 3.8.1`. There is no separate English or Devanagari detector — the Chinese detector generalizes well across scripts.

---

## Building from Source

Requires Python 3.12+.

### Quick build scripts

**Windows:**
```powershell
powershell -ExecutionPolicy Bypass -File .\build-exe.ps1
```

**Linux:**
```bash
chmod +x ./build-linux.sh
./build-linux.sh
```

**macOS (Apple Silicon):**
```bash
chmod +x ./build-macos.sh
./build-macos.sh
```

The Windows helper writes its bundle to `dist-windows/veridis-ocr-cli/`.
The Linux helper writes its bundle to `dist-linux/veridis-ocr-cli/`.
The macOS helper writes its bundle to `dist-macos/veridis-ocr-cli/`.
They create or reuse repo-local build environments at `.venv-build-windows/`, `.venv-build-linux/`, and `.venv-build-macos/`.
That keeps platform-specific artifacts separate when you build multiple targets from a shared checkout.

### 1. Create a virtual environment

**Windows:**
```powershell
python -m venv .venv
.\.venv\Scripts\activate
```

**Linux/macOS:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies and preload models

```bash
pip install pyinstaller
pip install -e .
python scripts/preload_models.py
```

### 3. Build the binary

```bash
pyinstaller --noconfirm rapidocr_cli.spec
```

The raw PyInstaller command writes to `dist/veridis-ocr-cli/`.
The helper scripts above instead write to `dist-windows/`, `dist-linux/`, and `dist-macos/` to keep platform builds separate.

---

## Notes

- **Cross-platform**: The CLI is built and tested for Windows, Linux, and Apple Silicon macOS in CI. PyInstaller does not cross-compile; build on the target OS.
- **macOS scope**: Only Apple Silicon (`arm64`) is currently built and published. Intel macOS builds are not included.
- **Self-contained**: Models are preloaded at build time so the binary never downloads anything at runtime.
- **Windows SmartScreen**: On first run, Windows may show an "unknown publisher" warning. Click "More info" then "Run anyway".
- **Distribution**: The `veridis-ocr-cli/` folder (or `_internal/` directory next to the exe on Windows) contains the bundled libraries and models. Keep them together.
