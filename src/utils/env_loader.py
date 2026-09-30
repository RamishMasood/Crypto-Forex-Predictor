import os
import sys

def load_env(env_path: str = None) -> bool:
    """
    Lightweight, zero-dependency .env loader using standard library only.
    Loads environment variables from .env into os.environ if not already defined.
    Guarantees cross-platform portability on any new clone without needing pip install python-dotenv.
    """
    if env_path is None:
        # Search relative to project root or current working directory
        possible_paths = [
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env"),
            os.path.join(os.getcwd(), ".env"),
            ".env"
        ]
        for p in possible_paths:
            if os.path.exists(p):
                env_path = p
                break

    if not env_path or not os.path.exists(env_path):
        return False

    try:
        with open(env_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip()
                    # Strip wrapping single/double quotes
                    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                        val = val[1:-1]
                    if key and key not in os.environ:
                        os.environ[key] = val
        return True
    except Exception:
        return False

# Auto-execute on import so importing src.utils.env_loader immediately populates environment
load_env()
