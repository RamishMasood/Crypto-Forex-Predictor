import os
import sys

os.environ.setdefault("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")
os.environ.setdefault("STREAMLIT_SERVER_HEADLESS", "true")
os.environ.setdefault("STREAMLIT_GLOBAL_DEVELOPMENT_MODE", "false")
os.environ.setdefault("STREAMLIT_SERVER_FILE_WATCHER_TYPE", "none")

if sys.stdout is None or sys.stderr is None:
    appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
    log_dir = os.path.join(appdata, "QuantTerminal")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "runtime.log")
    handle = open(log_path, "a", encoding="utf-8", buffering=1)
    if sys.stdout is None:
        sys.stdout = handle
    if sys.stderr is None:
        sys.stderr = handle
