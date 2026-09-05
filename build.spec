# PyInstaller spec: single windowed .exe with the tray icon embedded.
#   python -m uv run pyinstaller build.spec
# Output: dist/CFBTicker.exe

from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

a = Analysis(
    ["run.py"],  # not cfb_ticker/__main__.py: run as a script, its relative imports have no package
    pathex=["."],
    binaries=[],
    datas=[],
    hiddenimports=collect_submodules("cfb_ticker"),
    hookspath=[],
    runtime_hooks=[],
    # Qt modules the app never touches; leaving them out keeps the .exe well under 100 MB.
    excludes=[
        "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets", "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets", "PySide6.QtWebChannel", "PySide6.QtMultimedia",
        "PySide6.QtMultimediaWidgets", "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets",
        "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtSql", "PySide6.QtSvg",
        "PySide6.QtSvgWidgets", "PySide6.QtTest", "PySide6.QtXml", "PySide6.QtNetwork",
        "PySide6.QtPrintSupport", "PySide6.QtDesigner", "PySide6.QtHelp", "PySide6.QtUiTools",
        "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.Qt3DCore", "PySide6.Qt3DRender",
        "PySide6.QtBluetooth", "PySide6.QtNfc", "PySide6.QtPositioning", "PySide6.QtLocation",
        "PySide6.QtRemoteObjects", "PySide6.QtSensors", "PySide6.QtSerialPort", "PySide6.QtTextToSpeech",
        "PySide6.QtWebSockets", "PySide6.QtConcurrent", "PySide6.QtStateMachine", "PySide6.QtScxml",
        "tkinter", "unittest", "pydoc", "doctest", "xmlrpc",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="CFBTicker",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    icon="assets/icon.ico",
)
