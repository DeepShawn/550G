# -*- mode: python ; coding: utf-8 -*-
# PyInstaller onedir 构建配置。由 scripts/build-windows.ps1 调用：
#   python -m PyInstaller --noconfirm --clean packaging/windows.spec
# 资源统一放到 _internal/assets，运行时由 app.assets.resource_root() 通过 sys._MEIPASS 定位。
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent  # noqa: F821  (SPECPATH 由 PyInstaller 注入)
ASSETS = ROOT / "assets"

datas = [
    (str(ASSETS / "pets.json"), "assets"),
    (str(ASSETS / "dialogues.json"), "assets"),
    (str(ASSETS / "tray.ico"), "assets"),
    (str(ASSETS / "tray.png"), "assets"),
    (str(ASSETS / "pets" / "550g"), "assets/pets/550g"),
    (str(ASSETS / "pets" / "gpt_senpai"), "assets/pets/gpt_senpai"),
]

# 用不到的 Qt 模块，减小体积
excludes = [
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets", "PySide6.QtPdf",
    "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets",
    "PySide6.QtSvg", "PySide6.QtSvgWidgets", "PySide6.QtDBus", "PySide6.QtConcurrent",
    "PySide6.QtPrintSupport", "PySide6.QtXml", "PySide6.QtDesigner", "PySide6.QtUiTools",
    "PySide6.QtHelp", "tkinter", "unittest", "pytest", "PIL",
]

a = Analysis(  # noqa: F821
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=["PySide6.QtNetwork"],
    hookspath=[],
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="DesktopPets550G",
    icon=str(ASSETS / "tray.ico"),
    console=False,  # 调试时可临时改为 True
    disable_windowed_traceback=False,
    upx=False,
    version=str(ROOT / "packaging" / "version_info.txt"),
)
coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="DesktopPets550G",
)
