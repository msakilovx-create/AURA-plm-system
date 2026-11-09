"""Превью фото и GIF для карточки узла."""

from __future__ import annotations

from pathlib import Path

from .theme import PM_GROUP, TEXT

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff"}
MODEL_EXTS = {".stl", ".step", ".stp", ".stpz", ".obj"}


def is_image(path: str | Path) -> bool:
    return Path(path).suffix.lower() in IMAGE_EXTS


def is_model(path: str | Path) -> bool:
    return Path(path).suffix.lower() in MODEL_EXTS


def node_photo_path(node: dict) -> Path | None:
    raw = (node or {}).get("photo") or ""
    if not raw:
        return None
    p = Path(raw)
    return p if p.exists() else None


def node_model_path(node: dict) -> Path | None:
    if not node:
        return None
    candidates = [node.get("filePath") or ""]
    cf = node.get("cadFiles") or {}
    for key in ("stp", "native", "sw"):
        slot = cf.get(key) or {}
        candidates.append(slot.get("filePath") or "")
    for raw in candidates:
        if not raw:
            continue
        p = Path(raw)
        if p.exists() and is_model(p):
            return p
    return None


def load_preview(path: Path, size=(180, 200)):
    """Вернуть (single PhotoImage | None, frames list, durations list)."""
    try:
        from PIL import Image, ImageSequence, ImageTk
    except ImportError:
        return _load_tk(path, size)

    img = Image.open(path)
    w, h = size
    frames = []
    durs = []
    if path.suffix.lower() == ".gif" and getattr(img, "is_animated", False):
        for frame in ImageSequence.Iterator(img):
            fr = frame.convert("RGBA")
            fr.thumbnail(size, Image.Resampling.LANCZOS)
            canvas = Image.new("RGBA", size, (247, 243, 214, 255))
            x = (w - fr.width) // 2
            y = (h - fr.height) // 2
            canvas.paste(fr, (x, y), fr)
            frames.append(ImageTk.PhotoImage(canvas))
            durs.append(max(40, int(frame.info.get("duration", 100) or 100)))
        if frames:
            return frames[0], frames, durs
    fr = img.convert("RGBA")
    fr.thumbnail(size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", size, (247, 243, 214, 255))
    canvas.paste(fr, ((w - fr.width) // 2, (h - fr.height) // 2), fr)
    photo = ImageTk.PhotoImage(canvas)
    return photo, [photo], [100]


def _load_tk(path: Path, size):
    import tkinter as tk

    try:
        img = tk.PhotoImage(file=str(path))
    except tk.TclError:
        return None, [], []
    # subsample roughly
    iw, ih = img.width(), img.height()
    w, h = size
    if iw > w or ih > h:
        fx = max(1, iw // w)
        fy = max(1, ih // h)
        img = img.subsample(fx, fy)
    return img, [img], [100]


def placeholder_icon(kind: str) -> str:
    return {"assembly": "🧩", "part": "🔧", "project": "📁"}.get(kind, "📄")
