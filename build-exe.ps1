param(
    [switch]$Clean = $true
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvDir = Join-Path $root ".venv-build-windows"
$python = Join-Path $venvDir "Scripts\python.exe"
$modelsDir = Join-Path $venvDir "Lib\site-packages\rapidocr\models"
$buildDir = Join-Path $root "build-windows"
$distDir = Join-Path $root "dist-windows"
$distExe = Join-Path $distDir "veridis-ocr-cli\veridis-ocr-cli.exe"

if (-not (Test-Path $python)) {
    $created = $false
    if (Get-Command py -ErrorAction SilentlyContinue) {
        try {
            & py -3.12 -m venv $venvDir
            $created = $true
        }
        catch {
        }
    }

    if (-not $created) {
        & python -m venv $venvDir
    }
}

& $python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 'build-exe.ps1 requires Python 3.12 or newer')"
if ($LASTEXITCODE -ne 0) {
    throw "Windows build venv is not using Python 3.12+"
}

if ($Clean) {
    Remove-Item -Recurse -Force $buildDir -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force $distDir -ErrorAction SilentlyContinue
    if (Test-Path $modelsDir) {
        Get-ChildItem $modelsDir -Filter "*.onnx" | Remove-Item -Force -ErrorAction SilentlyContinue
    }
}

Push-Location $root
try {
    & $python -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) {
        throw "pip upgrade failed with exit code $LASTEXITCODE"
    }

    & $python -m pip install pyinstaller
    if ($LASTEXITCODE -ne 0) {
        throw "pyinstaller install failed with exit code $LASTEXITCODE"
    }

    & $python -m pip install -e .
    if ($LASTEXITCODE -ne 0) {
        throw "pip install failed with exit code $LASTEXITCODE"
    }

    & $python .\scripts\preload_models.py
    if ($LASTEXITCODE -ne 0) {
        throw "Model preload failed with exit code $LASTEXITCODE"
    }

    Write-Host "RapidOCR models ready"
    & $python -m PyInstaller --noconfirm --workpath $buildDir --distpath $distDir rapidocr_cli.spec
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE"
    }
    if (-not (Test-Path $distExe)) {
        throw "PyInstaller completed but expected artifact was not found at $distExe"
    }
    Write-Host "Built one-folder CLI at dist-windows\veridis-ocr-cli\veridis-ocr-cli.exe"
}
finally {
    Pop-Location
}
