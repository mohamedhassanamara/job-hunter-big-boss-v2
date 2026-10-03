"""Your own images and videos (My goals, shop item images), stored under
data/motivation/<workspace>/ with a random name. The type is checked by extension and by the
file's first bytes; the size limit is `motivation.max_upload_mb`."""

import re
import uuid
from pathlib import Path

from app.config import DATA_DIR

ROOT = DATA_DIR / "motivation"
IMAGES = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp",
          "gif": "image/gif"}
VIDEOS = {"mp4": "video/mp4", "webm": "video/webm", "mov": "video/quicktime"}
_NAME = re.compile(r"^[0-9a-f]{32}\.(?:png|jpg|webp|gif|mp4|webm|mov)$")


class UploadError(Exception):
    def __init__(self, message: str, status: int):
        super().__init__(message)
        self.status = status


def folder(workspace: str) -> Path:
    path = ROOT / ("demo" if workspace == "demo" else "real")
    path.mkdir(parents=True, exist_ok=True)
    return path


def _sniff(head: bytes) -> str | None:
    """The real type from the first bytes (an extension alone can lie)."""
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    if head[:4] == b"\x1a\x45\xdf\xa3":
        return "webm"
    if head[4:8] == b"ftyp":
        return "mov" if head[8:10] == b"qt" else "mp4"
    return None


def check(filename: str, head: bytes, size: int, max_mb: int,
          images_only: bool = False) -> tuple[str, str, str]:
    """(kind, extension, mime) or UploadError (413 too big, 415 wrong type)."""
    if size > max_mb * 1024 * 1024:
        raise UploadError(f"The file is larger than the {max_mb} MB limit (Settings → "
                          "Motivation)", 413)
    ext = (filename.rsplit(".", 1)[-1] if "." in filename else "").lower()
    ext = "jpg" if ext == "jpeg" else ext
    allowed = IMAGES if images_only else {**IMAGES, **VIDEOS}
    sniffed = _sniff(head)
    same = sniffed == ext or (sniffed == "mp4" and ext == "mov") or \
        (sniffed == "mov" and ext == "mp4")
    if ext not in allowed or not same:
        kinds = "PNG, JPG, WebP or GIF" if images_only else \
            "an image (PNG, JPG, WebP, GIF) or a video (MP4, WebM, MOV)"
        raise UploadError(f"Not {kinds}", 415)
    return ("video" if ext in VIDEOS else "image"), ext, allowed[ext]


def save(workspace: str, ext: str, data: bytes) -> str:
    name = f"{uuid.uuid4().hex}.{ext}"
    (folder(workspace) / name).write_bytes(data)
    return name


def path(workspace: str, name: str) -> Path | None:
    """The stored file, or None (only names this module created: no paths from outside)."""
    if not _NAME.match(name):
        return None
    p = folder(workspace) / name
    return p if p.is_file() else None


def remove(workspace: str, name: str | None) -> None:
    if name and (p := path(workspace, name)):
        p.unlink(missing_ok=True)


def mime(name: str) -> str:
    ext = name.rsplit(".", 1)[-1]
    return {**IMAGES, **VIDEOS}.get(ext, "application/octet-stream")
