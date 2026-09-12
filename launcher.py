"""
Quant Terminal desktop launcher.

Starts the Streamlit app locally and opens it in the browser so the
product runs like installed Windows software — no VS Code or CLI needed.
"""
from __future__ import annotations

import os
import socket
import sys
import threading
import time
import traceback
import webbrowser
from pathlib import Path


APP_NAME = "Quant Terminal"
HOST = "127.0.0.1"
PORT = 8501
URL = f"http://{HOST}:{PORT}"


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_home() -> Path:
    if _is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def bundle_dir() -> Path:
    if _is_frozen():
        return Path(getattr(sys, "_MEIPASS", app_home()))
    return Path(__file__).resolve().parent


def user_data_dir() -> Path:
    base = Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming")))
    path = base / "QuantTerminal"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _attach_stdio() -> Path:
    log_path = user_data_dir() / "launcher.log"
    if sys.stdout is None or sys.stderr is None:
        handle = open(log_path, "a", encoding="utf-8", buffering=1)
        if sys.stdout is None:
            sys.stdout = handle
        if sys.stderr is None:
            sys.stderr = handle
    return log_path


def _show_error(message: str) -> None:
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, message, APP_NAME, 0x10)
    except Exception:
        pass


def find_app_py() -> Path:
    candidates = [
        bundle_dir() / "app.py",
        app_home() / "app.py",
        app_home() / "_internal" / "app.py",
    ]
    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError("Could not find app.py in the application folder.")


def port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.4)
        return sock.connect_ex((HOST, port)) == 0


def wait_and_open_browser() -> None:
    for _ in range(90):
        if port_in_use(PORT):
            webbrowser.open(URL)
            return
        time.sleep(0.4)


def main() -> int:
    log_path = _attach_stdio()
    home = app_home()
    bundled = bundle_dir()
    os.chdir(str(home))

    for path in (str(bundled), str(home)):
        if path not in sys.path:
            sys.path.insert(0, path)

    os.environ["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
    os.environ["STREAMLIT_SERVER_HEADLESS"] = "true"
    os.environ["STREAMLIT_GLOBAL_DEVELOPMENT_MODE"] = "false"
    os.environ["STREAMLIT_SERVER_FILE_WATCHER_TYPE"] = "none"

    app_py = find_app_py()

    if port_in_use(PORT):
        webbrowser.open(URL)
        return 0

    threading.Thread(target=wait_and_open_browser, daemon=True).start()

    from streamlit.web import cli as stcli

    sys.argv = [
        "streamlit",
        "run",
        str(app_py),
        f"--server.port={PORT}",
        f"--server.address={HOST}",
        "--server.headless=true",
        "--global.developmentMode=false",
        "--server.fileWatcherType=none",
        "--server.runOnSave=false",
        "--browser.gatherUsageStats=false",
        "--browser.serverAddress=localhost",
        "--theme.base=dark",
    ]
    try:
        stcli.main()
        return 0
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 0
        if code not in (0, None):
            _show_error(
                f"{APP_NAME} stopped unexpectedly.\nDetails were written to:\n{log_path}"
            )
        return int(code or 0)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        log_path = _attach_stdio()
        with open(log_path, "a", encoding="utf-8") as handle:
            handle.write("\n" + traceback.format_exc())
        _show_error(f"{APP_NAME} failed to start.\nSee log:\n{log_path}")
        raise SystemExit(1)
