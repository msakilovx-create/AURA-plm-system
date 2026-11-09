"""Разбор состава: ссылки из CAD-файлов и иерархия STEP."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from .systems import all_cad_extensions, classify_cad_file

_SKIP_BITS = ("~$", "preview", "thumbnail", "template", "sldworks\\data")
_CAD_EXT = (
    ".sldprt", ".sldasm", ".slddrw", ".m3d", ".a3d", ".cdw", ".spw", ".frw",
    ".ipt", ".iam", ".idw", ".catpart", ".catproduct", ".fcstd", ".par", ".psm",
    ".asm", ".prt", ".stp", ".step", ".pdf",
)
_TOKEN_RE = re.compile(r"[A-Za-zА-Яа-я0-9][A-Za-zА-Яа-я0-9._\-]{2,160}", re.UNICODE)


def _is_cad_filename(name: str) -> bool:
    low = name.lower().strip()
    if len(low) < 5 or len(low) > 160:
        return False
    if any(bit in low for bit in _SKIP_BITS):
        return False
    return any(low.endswith(ext) for ext in _CAD_EXT)


def extract_referenced_names(path: Path) -> Counter:
    """Имена файлов, на которые ссылается сборка (без пути)."""
    counts: Counter = Counter()
    try:
        data = path.read_bytes()
    except OSError:
        return counts
    texts = [
        data.decode("latin-1", errors="ignore"),
        data.decode("utf-8", errors="ignore"),
        data.decode("utf-16le", errors="ignore"),
        data[1:].decode("utf-16le", errors="ignore") if len(data) > 1 else "",
        data.decode("utf-16be", errors="ignore"),
        data[1:].decode("utf-16be", errors="ignore") if len(data) > 1 else "",
    ]
    self_name = path.name.lower()
    best: Counter = Counter()
    for text in texts:
        local: Counter = Counter()
        text = text.replace("\x00", " ")
        for token in _TOKEN_RE.findall(text):
            name = Path(token.replace("\\", "/")).name
            if not _is_cad_filename(name):
                continue
            if name.lower() == self_name:
                continue
            local[name] += 1
        if len(local) > len(best):
            best = local
    counts.update(best)
    return counts


def index_files(root: Path) -> dict[str, Path]:
    index: dict[str, Path] = {}
    if not root.exists():
        return index
    exts = all_cad_extensions()
    if root.is_file():
        files = [root]
        root = root.parent
    else:
        files = [p for p in root.rglob("*") if p.is_file()]
    for p in files:
        if p.suffix.lower() not in exts and not _versioned(p):
            continue
        index.setdefault(p.name.lower(), p)
        index.setdefault(p.stem.lower(), p)
    return index


def _versioned(path: Path) -> bool:
    name = path.name.lower()
    return bool(re.search(r"\.(prt|asm|drw)\.\d+$", name))


def resolve_ref(name: str, index: dict[str, Path], folder: Path) -> Path | None:
    key = Path(name).name.lower()
    if key in index:
        return index[key]
    stem = Path(name).stem.lower()
    if stem in index:
        return index[stem]
    direct = folder / Path(name).name
    if direct.exists():
        return direct
    return None


def parse_step_tree(path: Path) -> dict | None:
    """Грубое дерево сборки STEP: корень и дети PRODUCT."""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    if "ISO-10303" not in text.upper() and "STEP" not in text[:200].upper() and not re.search(r"\bPRODUCT\s*\(", text, re.I):
        # всё равно пробуем, если есть PRODUCT
        if "PRODUCT" not in text.upper():
            return None
    products = []
    for m in re.finditer(
        r"#(\d+)\s*=\s*PRODUCT\s*\(\s*'([^']*)'\s*,\s*'([^']*)'",
        text,
        re.IGNORECASE,
    ):
        pid, ident, name = m.group(1), m.group(2), m.group(3)
        label = (name or ident or f"PRODUCT_{pid}").strip() or f"PRODUCT_{pid}"
        if label.upper() in {"", "NONE", "NULL"}:
            continue
        products.append({"id": pid, "name": label, "ident": ident})
    if not products:
        return None
    nauo = re.findall(
        r"NEXT_ASSEMBLY_USAGE_OCCURRENCE\s*\([^;]*?#(\d+)\s*,\s*#(\d+)",
        text,
        re.IGNORECASE,
    )
    root_name = products[0]["name"]
    children: Counter = Counter()
    if len(products) > 1:
        for p in products[1:]:
            children[p["name"]] += 1
    return {
        "name": root_name,
        "file": path,
        "kind": "assembly" if (nauo or len(products) > 1) else "part",
        "children": children,
        "products": products,
    }


def list_cad_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    files = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        _sys, kind = classify_cad_file(p)
        if kind in {"part", "assembly", "drawing"} or p.suffix.lower() in {".stp", ".step", ".pdf"}:
            files.append(p)
    return files
