# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build of aniREF: one folder (dist/aniREF), windowed, no Python needed.

    pyinstaller --noconfirm --clean packaging/aniref.spec

Normally run through packaging/build.ps1, which also makes the icon, runs the
selftest on the result and zips it. Onedir rather than onefile: starts faster
(nothing to unpack on every launch), trips antivirus less, and keeps the Qt
(LGPL) libraries as replaceable files next to the exe.
"""

import re
import shutil
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules
from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo,
    StringFileInfo,
    StringStruct,
    StringTable,
    VarFileInfo,
    VarStruct,
    VSVersionInfo,
)

HERE = Path(SPECPATH)  # noqa: F821 (defined by PyInstaller)
ROOT = HERE.parent
SRC = ROOT / "src"

# The version lives in one place; the file may carry a BOM.
VERSION = re.search(
    r'__version__\s*=\s*["\']([^"\']+)["\']', (SRC / "aniref" / "__init__.py").read_text("utf-8-sig")
).group(1)
_nums = [int(n) for n in re.findall(r"\d+", VERSION)[:4]]
VERSION_TUPLE = tuple(_nums + [0] * (4 - len(_nums)))

# --------------------------------------------------------------------------- what goes in

# The whole package, whatever modules exist at build time: features are added
# all the time and some are only imported lazily (inside functions).
hiddenimports = collect_submodules("aniref")
# The update checker needs QtNetwork (+ its TLS plugins for https) even if it is
# imported lazily or temporarily switched off.
hiddenimports += ["PySide6.QtNetwork"]
datas = collect_data_files("aniref")

# Qt modules the app does not use. Excluding the Python module also stops its
# hook from collecting the matching Qt DLLs, plugins and translations.
# Kept on purpose: QtCore/Gui/Widgets, QtSvg (icons are SVG drawn in code) and
# QtNetwork (update checker uses QNetworkAccessManager).
_QT_UNUSED = [
    "Qt3DAnimation", "Qt3DCore", "Qt3DExtras", "Qt3DInput", "Qt3DLogic", "Qt3DRender",
    "QtAxContainer", "QtBluetooth", "QtCharts", "QtConcurrent", "QtDataVisualization", "QtDBus",
    "QtDesigner", "QtGraphs", "QtGraphsWidgets", "QtHelp", "QtHttpServer", "QtLocation",
    "QtMultimedia", "QtMultimediaWidgets", "QtNetworkAuth", "QtNfc", "QtOpenGL", "QtOpenGLWidgets",
    "QtPdf", "QtPdfWidgets", "QtPositioning", "QtQml", "QtQuick", "QtQuick3D", "QtQuickControls2",
    "QtQuickTest", "QtQuickWidgets", "QtRemoteObjects", "QtScxml", "QtSensors", "QtSerialBus",
    "QtSerialPort", "QtSpatialAudio", "QtSql", "QtStateMachine", "QtTest", "QtTextToSpeech",
    "QtUiTools", "QtWebChannel", "QtWebEngineCore", "QtWebEngineQuick", "QtWebEngineWidgets",
    "QtWebSockets", "QtWebView", "QtXml",
]
excludes = [f"PySide6.{m}" for m in _QT_UNUSED] + [
    "tkinter", "_tkinter", "turtle", "turtledemo", "idlelib",
    "pytest", "_pytest", "pydoc_data", "lib2to3",
]

# Collected by the Qt hooks even with the modules above excluded (plugin
# dependencies / "extra binaries"). Matched against the path inside the bundle.
_DROP = [
    # Software OpenGL fallback, only for QtQuick/QOpenGLWidget; widgets paint with the raster engine.
    r"opengl32sw\.dll$",
    # Image format plugins that drag in big libraries (qpdf -> Qt6Pdf) or formats nobody feeds a
    # reference tool. Kept: ico, jpeg, png (built into QtGui), gif, svg, webp, tiff, tga, bmp.
    r"plugins[\\/]imageformats[\\/]q(pdf|icns|wbmp)\.dll$",
    # On-screen keyboard: pulls in QtQuick + QtQml (~20 MB) for touch-only kiosks.
    r"plugins[\\/]platforminputcontexts[\\/]",
    # Touch-screen (TUIO) input over the network.
    r"plugins[\\/]generic[\\/]",
    # Experimental Direct2D platform; qwindows is the real one (qoffscreen stays for headless runs).
    r"plugins[\\/]platforms[\\/]qdirect2d\.dll$",
    # HTTPS goes through Windows' own TLS (schannel: system certificate store, corporate proxies).
    # Without this the hook grabs whatever OpenSSL 3 is on the build machine's PATH (Git's mingw
    # copy on GitHub runners) and Qt would prefer it. Python's own libssl-1_1 stays (ssl module).
    r"plugins[\\/]tls[\\/]q(openssl|certonly)backend\.dll$",
    r"(^|[\\/])lib(ssl|crypto)-3(-x64)?\.dll$",
    # QtQuick-only / unused Qt libraries, if a plugin dependency still reached them.
    r"Qt6(Pdf|Qml|QmlMeta|QmlModels|QmlWorkerScript|Quick|QuickControls2|QuickTemplates2|"
    r"VirtualKeyboard|VirtualKeyboardQml|OpenGL|OpenGLWidgets)\.dll$",
    # Qt's own UI translations: aniREF has its own ko/en strings; keep Qt's for those two only
    # (standard dialog buttons such as "Cancel" in QMessageBox/QFileDialog).
    r"translations[\\/](?!qt(base)?_(ko|en)\.qm$)[^\\/]+\.qm$",
]
_drop_re = re.compile("|".join(f"(?:{p})" for p in _DROP), re.IGNORECASE)


def _keep(toc):
    return [entry for entry in toc if not _drop_re.search(entry[0])]


a = Analysis(  # noqa: F821
    [str(SRC / "aniref" / "__main__.py")],
    pathex=[str(SRC)],  # the src layout, without relying on how `pip install -e` exposes it
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,  # asserts and docstrings stay (argparse/help text, clearer tracebacks)
)
a.binaries = _keep(a.binaries)
a.datas = _keep(a.datas)

pyz = PYZ(a.pure)  # noqa: F821

version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=VERSION_TUPLE, prodvers=VERSION_TUPLE, mask=0x3F, flags=0x0, OS=0x40004,
                      fileType=0x1, subtype=0x0, date=(0, 0)),
    kids=[
        StringFileInfo([
            StringTable("040904B0", [
                StringStruct("CompanyName", "aniREF"),
                StringStruct("FileDescription", "aniREF - animation reference tool"),
                StringStruct("FileVersion", VERSION),
                StringStruct("InternalName", "aniREF"),
                StringStruct("LegalCopyright", "GPL-3.0-or-later"),
                StringStruct("OriginalFilename", "aniREF.exe"),
                StringStruct("ProductName", "aniREF"),
                StringStruct("ProductVersion", VERSION),
            ])
        ]),
        VarFileInfo([VarStruct("Translation", [0x0409, 1200])]),
    ],
)

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="aniREF",
    icon=str(HERE / "aniref.ico"),
    version=version_info,
    console=False,  # windowed: no console window behind the app
    # Keep PyInstaller's error dialog for a crash before logging is up: it is
    # the only thing a colleague would see. (--selftest catches everything itself.)
    disable_windowed_traceback=False,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX-packed DLLs trigger antivirus false positives and break some Qt plugins
)

coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="aniREF",
)

# --------------------------------------------------------------------------- next to the exe

# Files users should see at the top of the folder (not buried in _internal):
# the license the FFmpeg/x264 bundle requires, and the Maya scripts (DESIGN.md 8).
_app_dir = Path(DISTPATH) / "aniREF"  # noqa: F821
if (ROOT / "LICENSE").exists():
    shutil.copy2(ROOT / "LICENSE", _app_dir / "LICENSE.txt")
if (ROOT / "maya").is_dir():
    shutil.copytree(ROOT / "maya", _app_dir / "maya", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
