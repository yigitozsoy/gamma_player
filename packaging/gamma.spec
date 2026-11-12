# -*- mode: python ; coding: utf-8 -*-
# PyInstaller tanımı.  Doğrudan değil, packaging\build.ps1 üzerinden çalıştırın.
import os
from PyInstaller.utils.hooks import collect_all, collect_dynamic_libs

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

datas = [(os.path.join(ROOT, "gammaplayer", "assets"), os.path.join("gammaplayer", "assets"))]
binaries = []
hiddenimports = [
    "PyQt6.QtSvg", "PyQt6.QtNetwork", "vlc",
    "imagecodecs._jpegxl", "imagecodecs._shared", "imagecodecs._imcd",
]
for pkg in ("imageio_ffmpeg", "pillow_heif"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# imagecodecs'in tamamı ~45 MB; yalnızca JPEG XL kodlayıcısı gerekli
binaries += [x for x in collect_dynamic_libs("imagecodecs")
             if any(k in os.path.basename(x[0]).lower() for k in ("jpegxl", "jxl", "brotli", "hwy", "shared", "imcd"))]

EXCLUDES = [
    "tkinter", "unittest", "pydoc", "test", "lib2to3", "matplotlib", "scipy", "pandas", "IPython",
    "PyQt6.QtWebEngineCore", "PyQt6.QtWebEngineWidgets", "PyQt6.QtWebChannel", "PyQt6.QtQml",
    "PyQt6.QtQuick", "PyQt6.QtQuickWidgets", "PyQt6.Qt3DCore", "PyQt6.QtBluetooth", "PyQt6.QtSql",
    "PyQt6.QtTest", "PyQt6.QtDesigner", "PyQt6.QtHelp", "PyQt6.QtPdf", "PyQt6.QtPdfWidgets",
    "PyQt6.QtMultimedia", "PyQt6.QtMultimediaWidgets", "PyQt6.QtPositioning", "PyQt6.QtSensors",
    "PyQt6.QtSerialPort", "PyQt6.QtOpenGL", "PyQt6.QtOpenGLWidgets", "PyQt6.QtCharts",
]

a = Analysis(
    [os.path.join(ROOT, "main.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="gamma",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    version=os.path.join(SPECPATH, "version_info.txt"),
    icon=[os.path.join(ROOT, "gammaplayer", "assets", "logo.ico")],
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="gamma")
