# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.building.build_main import Analysis, COLLECT, EXE, PYZ
from PyInstaller.utils.hooks import collect_all, copy_metadata

spec_dir = os.path.dirname(os.path.abspath(SPEC))
root = os.path.dirname(spec_dir)

datas = []
binaries = []
hiddenimports = [
    "streamlit",
    "streamlit.web.cli",
    "streamlit.runtime.scriptrunner.magic_funcs",
    "streamlit_autorefresh",
    "MetaTrader5",
    "sklearn.utils._cython_blas",
    "sklearn.neighbors._typedefs",
    "sklearn.neighbors._quad_tree",
    "sklearn.tree._utils",
    "scipy.special.cython_special",
    "joblib",
    "altair",
    "pyarrow",
    "tornado",
    "tornado.web",
    "tornado.httpserver",
    "watchdog",
    "packaging",
    "importlib_metadata",
    "jsonschema",
    "git",
    "rich",
    "ccxt",
    "yfinance",
    "matplotlib",
    "PIL",
]

packages_to_collect = [
    "streamlit",
    "streamlit_autorefresh",
    "altair",
    "sklearn",
    "scipy",
    "matplotlib",
    "pandas",
    "numpy",
    "ccxt",
    "yfinance",
    "rich",
    "jsonschema",
    "pydeck",
    "pyarrow",
    "tornado",
    "blinker",
    "git",
    "tzdata",
]

for pkg in packages_to_collect:
    try:
        pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
        datas += pkg_datas
        binaries += pkg_binaries
        hiddenimports += pkg_hidden
    except Exception:
        pass

for pkg in ("streamlit", "jsonschema", "rich", "altair"):
    try:
        datas += copy_metadata(pkg)
    except Exception:
        pass

datas += [
    (os.path.join(root, "app.py"), "."),
    (os.path.join(root, "src"), "src"),
]

a = Analysis(
    [os.path.join(root, "launcher.py")],
    pathex=[root],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[os.path.join(spec_dir, "rthook_quant.py")],
    excludes=["pytest", "unittest"],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="QuantTerminal",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    icon=os.path.join(spec_dir, "quant_terminal.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="QuantTerminal",
)
