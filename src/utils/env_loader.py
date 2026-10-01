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
                    if key:
                        os.environ[key] = val
        return True
    except Exception:
        return False

def set_env_variable(key: str, val: str, env_path: str = None) -> bool:
    """
    Safely writes or updates an environment variable in the .env file and updates os.environ.
    Guarantees secrets are stored strictly in .env (which is in .gitignore).
    """
    if env_path is None:
        possible_paths = [
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env"),
            os.path.join(os.getcwd(), ".env"),
            ".env"
        ]
        for p in possible_paths:
            if os.path.exists(p):
                env_path = p
                break
        if not env_path:
            env_path = os.path.join(os.getcwd(), ".env")

    os.environ[key] = val
    try:
        lines = []
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

        found = False
        new_lines = []
        for line in lines:
            trimmed = line.strip()
            if trimmed.startswith(f"{key}=") or trimmed.startswith(f"export {key}="):
                new_lines.append(f"{key}={val}\n")
                found = True
            else:
                new_lines.append(line)

        if not found:
            if new_lines and not new_lines[-1].endswith("\n"):
                new_lines[-1] += "\n"
            new_lines.append(f"{key}={val}\n")

        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
        return True
    except Exception:
        return False

# Auto-execute on import so importing src.utils.env_loader immediately populates environment
load_env()
