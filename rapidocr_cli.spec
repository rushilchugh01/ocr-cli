# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules, copy_metadata

datas = collect_data_files("rapidocr")
datas += collect_data_files("shapely")
datas += copy_metadata("rapidocr")
datas += copy_metadata("onnxruntime")

binaries = collect_dynamic_libs("onnxruntime")
binaries += collect_dynamic_libs("shapely")
hiddenimports = collect_submodules("rapidocr")
hiddenimports += collect_submodules("shapely")

a = Analysis(
    ["src/rapidocr_cli/cli.py"],
    pathex=["src"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="rapidocr-cli",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="rapidocr-cli",
)
