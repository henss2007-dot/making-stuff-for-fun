# PyInstaller build file: pyinstaller bookpress.spec
# Produces a single-file BookPress app with the editor page, fonts data and hyphenation dictionaries inside.
import os
from PyInstaller.utils.hooks import collect_data_files

datas = [("bookpress/ui.html", "bookpress")]
datas += collect_data_files("reportlab")   # built-in font metrics and CID font maps
datas += collect_data_files("pyphen")      # hyphenation dictionaries

a = Analysis(
    ["bookpress_app.py"],
    pathex=["."],
    datas=datas,
    hiddenimports=["pypdf", "pyphen", "PIL.Image", "PIL.ImageDraw"],
    excludes=["tkinter", "matplotlib", "numpy", "scipy", "pytest", "IPython"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=os.environ.get("BOOKPRESS_EXE_NAME", "BookPress"),
    console=True,
    upx=False,
    icon=None,
)
