"""Uploaded resume files: <UPLOAD_DIR>/<safe user id>/resume.<ext>. Files are never served back."""
import hashlib
import re
import shutil
from pathlib import Path

from core import config

UPLOAD_DIR = Path(config.UPLOAD_DIR)
SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def user_dir(user_id: str) -> Path:
    """The user's folder. An id that isn't a plain token is hashed, so it can't form a path."""
    name = user_id if SAFE_ID.match(user_id) else hashlib.sha256(user_id.encode()).hexdigest()
    return UPLOAD_DIR / name


def save(user_id: str, kind: str, content: bytes) -> Path:
    """Store the file, replacing any earlier upload."""
    folder = user_dir(user_id)
    delete_user_files(user_id)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"resume.{kind}"
    path.write_bytes(content)
    return path


def delete_user_files(user_id: str) -> None:
    shutil.rmtree(user_dir(user_id), ignore_errors=True)
