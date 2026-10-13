import json
import os
import tempfile
from pathlib import Path


def data_dir() -> Path:
    return Path(os.environ.get("HUMANIZER_DATA_DIR", Path.home() / "Library/Application Support/Humanizer"))


def app_path() -> Path:
    return Path(os.environ.get("HUMANIZER_APP_PATH", Path.home() / "Applications/Humanizer.app"))


def private_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(0o700)
    return path


def atomic_json(path: Path, value: dict):
    private_dir(path.parent)
    fd, name = tempfile.mkstemp(prefix=".write-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def read_json(path: Path, default: dict) -> dict:
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else default
    except (OSError, ValueError):
        return default
