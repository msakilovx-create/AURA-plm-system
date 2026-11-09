"""Хранилище файлов AURA PLM: структура проекта и копирование при импорте/создании."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from .cad.systems import CAD_SYSTEMS, classify_cad_file, get_system, slot_for_path
from .model import ensure_cad_files

CREATE_NO_WINDOW = 0x08000000

SUBDIRS = ("native", "step", "stl", "drawings", "photos", "docs")

_README = """AURA PLM — хранилище файлов
==============================
Каждый проект лежит в Projects\\<имя>__<id>\\

  00_Project      документы проекта
  01_Assemblies   сборки (native / step / stl / drawings / photos / docs)
  02_Parts        детали (те же папки)
  03_Imports      исходники выгрузки CAD / Teamcenter

При импорте файлы копируются сюда. Новая деталь или сборка сразу получает папки.
Открывайте модели из AURA — CAD запускается с файла в этом хранилище.
"""


def default_vault_root(username: str | None = None) -> Path:
    base = Path.home() / "Documents" / "AURA_Vault"
    if username:
        return base / slug(username, "user")
    return base


def vault_root(doc: dict | None, username: str | None = None) -> Path:
    raw = ((doc or {}).get("vault") or {}).get("root") or ""
    if raw:
        return Path(raw)
    owner = username or ((doc or {}).get("owner") or "")
    return default_vault_root(owner or None)


def set_vault_root(doc: dict, path: str | Path) -> Path:
    doc.setdefault("vault", {})["root"] = str(Path(path).resolve())
    return init_vault(Path(path))


def init_vault(root: Path | None = None) -> Path:
    root = Path(root) if root else default_vault_root()
    (root / "Projects").mkdir(parents=True, exist_ok=True)
    readme = root / "README.txt"
    if not readme.exists():
        readme.write_text(_README, encoding="utf-8")
    idx = root / "vault.json"
    if not idx.exists():
        idx.write_text(json.dumps({"app": "AURA PLM Vault", "version": 1}, ensure_ascii=False, indent=2), encoding="utf-8")
    return root


def slug(text: str, fallback: str = "item") -> str:
    s = re.sub(r'[<>:"/\\|?*\n\r\t]', "_", str(text or "").strip())
    s = re.sub(r"\s+", "_", s)
    s = s.strip(" ._")[:72]
    return s or fallback


def _id6(node: dict) -> str:
    return str(node.get("id") or "x")[-6:]


def _label(node: dict) -> str:
    return (node.get("designation") or node.get("code") or node.get("name") or "item").strip()


def project_dir(doc: dict, prj: dict) -> Path:
    name = slug(_label(prj), "project")
    return vault_root(doc) / "Projects" / f"{name}__{_id6(prj)}"


def node_dir(doc: dict, prj: dict, node: dict, kind: str) -> Path:
    root = project_dir(doc, prj)
    if kind == "project":
        return root / "00_Project"
    folder = "01_Assemblies" if kind == "assembly" else "02_Parts"
    return root / folder / f"{slug(_label(node), kind)}__{_id6(node)}"


def slot_dir_for_file(node_folder: Path, path: Path) -> Path:
    ext = path.suffix.lower()
    if ext in {".stp", ".step", ".stpz", ".p21"}:
        return node_folder / "step"
    if ext == ".stl":
        return node_folder / "stl"
    if ext in {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff"}:
        return node_folder / "photos"
    if ext in {".pdf", ".dwg", ".dxf", ".slddrw", ".cdw", ".idw", ".spw", ".frw", ".dft"}:
        return node_folder / "drawings"
    if ext in {".txt", ".doc", ".docx", ".xls", ".xlsx", ".json", ".xml", ".plmxml"}:
        return node_folder / "docs"
    return node_folder / "native"


def ensure_node_storage(doc: dict, prj: dict, node: dict, kind: str) -> Path:
    init_vault(vault_root(doc))
    folder = node_dir(doc, prj, node, kind)
    for sub in SUBDIRS:
        (folder / sub).mkdir(parents=True, exist_ok=True)
    if kind == "project":
        (project_dir(doc, prj) / "03_Imports").mkdir(parents=True, exist_ok=True)
    sidecar = {
        "id": node.get("id"),
        "kind": kind,
        "name": node.get("name"),
        "designation": node.get("designation") or node.get("code") or "",
        "revision": node.get("revision") or "",
    }
    (folder / "docs" / "_aura.json").write_text(json.dumps(sidecar, ensure_ascii=False, indent=2), encoding="utf-8")
    hint = folder / "native" / "СОХРАНИТЕ_МОДЕЛЬ_СЮДА.txt"
    if not hint.exists() and kind in {"part", "assembly"}:
        hint.write_text(
            f"Узел AURA: {node.get('name')}\n"
            f"Обозначение: {node.get('designation') or node.get('code') or '—'}\n\n"
            "Сохраните модель CAD в эту папку native\\.\n"
            "STEP — в папку step\\, STL — в stl\\, чертежи — в drawings\\, фото — в photos\\.\n",
            encoding="utf-8",
        )
    node["vaultPath"] = str(folder)
    node["folderPath"] = str(folder)
    return folder


def remove_node_storage(doc: dict, prj: dict, node: dict, kind: str) -> None:
    folder = node_dir(doc, prj, node, kind)
    target = project_dir(doc, prj) if kind == "project" else folder
    if target.exists() and is_in_vault(doc, target):
        shutil.rmtree(target, ignore_errors=True)


def is_in_vault(doc: dict, path: Path) -> bool:
    try:
        path.resolve().relative_to(vault_root(doc).resolve())
        return True
    except ValueError:
        return False


def ingest_file(doc: dict, prj: dict, node: dict, kind: str, src: str | Path, as_photo=False) -> Path:
    src = Path(src)
    folder = ensure_node_storage(doc, prj, node, kind)
    if not src.exists() or not src.is_file():
        raise FileNotFoundError(src)
    if is_in_vault(doc, src):
        dest = src.resolve()
    else:
        dest_dir = folder / "photos" if as_photo else slot_dir_for_file(folder, src)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / src.name
        if dest.exists() and dest.resolve() != src.resolve():
            stem, ext = dest.stem, dest.suffix
            n = 2
            while dest.exists():
                dest = dest_dir / f"{stem}_{n}{ext}"
                n += 1
        if dest.resolve() != src.resolve():
            shutil.copy2(src, dest)
    ensure_cad_files(node)
    if as_photo:
        node["photo"] = str(dest)
        return dest
    node["filePath"] = str(dest)
    node["folderPath"] = str(dest.parent)
    slot = slot_for_path(dest)
    node["cadFiles"][slot]["filePath"] = str(dest)
    node["cadFiles"][slot]["folderPath"] = str(dest.parent)
    if dest.suffix.lower() in {".sldprt", ".sldasm", ".slddrw"}:
        node["cadFiles"]["sw"]["filePath"] = str(dest)
        node["cadFiles"]["sw"]["folderPath"] = str(dest.parent)
    return dest


def ingest_project(doc: dict, prj: dict, source: str | Path | None = None) -> int:
    """Скопировать все привязанные файлы проекта в хранилище. Возвращает число копий."""
    ensure_node_storage(doc, prj, prj, "project")
    copied = 0
    if source:
        src = Path(source)
        imports = project_dir(doc, prj) / "03_Imports"
        imports.mkdir(parents=True, exist_ok=True)
        if src.is_file():
            dest = imports / src.name
            if not dest.exists():
                shutil.copy2(src, dest)
                copied += 1
        elif src.is_dir():
            marker = imports / (slug(src.name, "import") + "_source.txt")
            marker.write_text(str(src.resolve()), encoding="utf-8")

    def take(node, kind):
        nonlocal copied
        ensure_node_storage(doc, prj, node, kind)
        paths = []
        if node.get("filePath"):
            paths.append(node["filePath"])
        if node.get("photo"):
            try:
                ingest_file(doc, prj, node, kind, node["photo"], as_photo=True)
                copied += 1
            except Exception:
                pass
        cf = node.get("cadFiles") or {}
        for key in ("sw", "stp", "pdf", "native"):
            p = (cf.get(key) or {}).get("filePath")
            if p:
                paths.append(p)
        seen_src = set()
        for raw in paths:
            if not raw:
                continue
            p = Path(raw)
            if not p.exists():
                continue
            key = str(p.resolve()).lower()
            if key in seen_src:
                continue
            seen_src.add(key)
            if is_in_vault(doc, p):
                continue
            try:
                ingest_file(doc, prj, node, kind, p)
                copied += 1
            except Exception:
                continue

    take(prj, "project")

    def walk(asm):
        take(asm, "assembly")
        for p in asm.get("parts") or []:
            take(p, "part")
        for nested in asm.get("assemblies") or []:
            walk(nested)

    for a in prj.get("assemblies") or []:
        walk(a)
    return copied


def preferred_cad_file(node: dict) -> Path | None:
    ensure_cad_files(node)
    for key in ("native", "sw", "stp"):
        raw = (node.get("cadFiles") or {}).get(key, {}).get("filePath")
        if raw and Path(raw).exists():
            return Path(raw)
    raw = node.get("filePath")
    if raw and Path(raw).exists():
        return Path(raw)
    vault = node.get("vaultPath")
    if vault:
        native = Path(vault) / "native"
        if native.exists():
            files = [p for p in native.iterdir() if p.is_file() and p.suffix.lower() not in {".txt", ".json"}]
            if files:
                return files[0]
    return None


def find_cad_executable(system_id: str) -> Path | None:
    from .cad.detect import _path_hit

    sys = get_system(system_id)
    if not sys or not sys.exes:
        return None
    if system_id == "nx":
        base = os.environ.get("UGII_BASE_DIR") or os.environ.get("UGII_ROOT_DIR")
        if base:
            cand = Path(base) / "NXBIN" / "ugraf.exe"
            if cand.exists():
                return cand
    install = _path_hit(sys)
    roots = [Path(install)] if install else []
    for env in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432"):
        v = os.environ.get(env)
        if v:
            roots.append(Path(v))
    for exe in sys.exes:
        which = shutil.which(exe)
        if which:
            return Path(which)
        for root in roots:
            if not root.exists():
                continue
            for cand in (
                root / exe,
                root / "BIN" / exe,
                root / "Bin" / exe,
                root / "NXBIN" / exe,
                root / "SOLIDWORKS" / exe,
            ):
                if cand.exists():
                    return cand
            try:
                hits = list(root.glob(exe)) + list(root.glob(f"*/{exe}")) + list(root.glob(f"*/*/{exe}"))
            except OSError:
                hits = []
            if hits:
                return hits[0]
    return None


def launch_cad(system_id: str | None, target: Path) -> None:
    """Открыть файл или папку в CAD. system_id=None — ассоциация Windows."""
    target = Path(target)
    exe = find_cad_executable(system_id) if system_id and system_id not in {"step", "teamcenter"} else None
    if target.is_file():
        if exe:
            subprocess.Popen([str(exe), str(target)], cwd=str(target.parent), creationflags=CREATE_NO_WINDOW)
            return
        os.startfile(str(target))  # type: ignore[attr-defined]
        return
    folder = target if target.is_dir() else target.parent
    folder.mkdir(parents=True, exist_ok=True)
    if exe:
        subprocess.Popen([str(exe)], cwd=str(folder), creationflags=CREATE_NO_WINDOW)
        return
    os.startfile(str(folder))  # type: ignore[attr-defined]


def open_node_in_cad(doc: dict, prj: dict, node: dict, kind: str, system_id: str | None = None) -> Path:
    folder = ensure_node_storage(doc, prj, node, kind)
    path = preferred_cad_file(node)
    if path is None:
        path = folder / "native"
    if system_id is None and path.is_file():
        sys, _k = classify_cad_file(path)
        system_id = sys.id if sys else None
    launch_cad(system_id, path)
    return path
