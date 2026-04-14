param(
    [switch]$Clean = $true
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $root "NOSProjectsothersocrrapidocr.venv-win\Scripts\python.exe"
$modelsDir = Join-Path $root "NOSProjectsothersocrrapidocr.venv-win\Lib\site-packages\rapidocr\models"
$distExe = Join-Path $root "dist\veridis-ocr-cli\veridis-ocr-cli.exe"

if (-not (Test-Path $python)) {
    throw "Windows venv not found at $python"
}

if ($Clean) {
    Remove-Item -Recurse -Force (Join-Path $root "build") -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force (Join-Path $root "dist") -ErrorAction SilentlyContinue
    if (Test-Path $modelsDir) {
        Get-ChildItem $modelsDir -Filter "*.onnx" | Remove-Item -Force -ErrorAction SilentlyContinue
    }
}

Push-Location $root
try {
    & $python -m pip install -e .
    if ($LASTEXITCODE -ne 0) {
        throw "pip install failed with exit code $LASTEXITCODE"
    }

    & $python .\scripts\preload_models.py
    if ($LASTEXITCODE -ne 0) {
        throw "Model preload failed with exit code $LASTEXITCODE"
    }

    Write-Host "RapidOCR models ready"
    & $python -m PyInstaller --noconfirm rapidocr_cli.spec
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE"
    }
    if (-not (Test-Path $distExe)) {
        throw "PyInstaller completed but expected artifact was not found at $distExe"
    }
    Write-Host "Built one-folder CLI at dist\veridis-ocr-cli\veridis-ocr-cli.exe"
}
finally {
    Pop-Location
}
