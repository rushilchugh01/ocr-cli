param(
    [switch]$Clean = $true
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $root "NOSProjectsothersocrrapidocr.venv-win\Scripts\python.exe"
$pyinstaller = Join-Path $root "NOSProjectsothersocrrapidocr.venv-win\Scripts\pyinstaller.exe"
$modelsDir = Join-Path $root "NOSProjectsothersocrrapidocr.venv-win\Lib\site-packages\rapidocr\models"

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
    & $python .\scripts\preload_models.py
    Write-Host "RapidOCR models ready"
    & $pyinstaller --noconfirm rapidocr_cli.spec
    Write-Host "Built one-folder CLI at dist\rapidocr-cli\rapidocr-cli.exe"
}
finally {
    Pop-Location
}
