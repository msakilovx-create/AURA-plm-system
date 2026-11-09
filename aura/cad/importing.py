"""Выгрузка CAD-проекта в дерево AURA PLM."""

from __future__ import annotations

import os
import subprocess
from collections import Counter
from pathlib import Path

from ..model import ensure_cad_files, new_assembly, new_part, new_project, uid
from .live import GrabError, active_document_path, nx_looks_managed, teamcenter_running
from .parse import extract_referenced_names, index_files, list_cad_files, parse_step_tree, resolve_ref
from .systems import classify_cad_file, slot_for_path

CREATE_NO_WINDOW = 0x08000000


def attach_cad_file(node: dict, path: Path) -> None:
    path = path.resolve()
    ensure_cad_files(node)
    node["filePath"] = str(path)
    node["folderPath"] = str(path.parent)
    slot = slot_for_path(path)
    node["cadFiles"][slot]["filePath"] = str(path)
    node["cadFiles"][slot]["folderPath"] = str(path.parent)
    if path.suffix.lower() in {".sldprt", ".sldasm", ".slddrw"}:
        node["cadFiles"]["sw"]["filePath"] = str(path)
        node["cadFiles"]["sw"]["folderPath"] = str(path.parent)


def _ensure_assembly_node(node: dict) -> dict:
    if "assemblies" in node and "parts" in node:
        return node
    wrap = new_assembly(node.get("name") or "Сборка")
    wrap["parts"] = [node]
    wrap["filePath"] = node.get("filePath") or ""
    wrap["folderPath"] = node.get("folderPath") or ""
    return wrap


def _build_from_assembly(asm_path: Path, index: dict[str, Path], visited: set[str] | None = None) -> dict:
    visited = visited if visited is not None else set()
    key = str(asm_path.resolve()).lower()
    if key in visited:
        node = new_part(asm_path.stem)
        node["productType"] = "Заимствованное"
        attach_cad_file(node, asm_path)
        return node
    visited.add(key)

    sys, kind = classify_cad_file(asm_path)
    if kind != "assembly" and asm_path.suffix.lower() not in {".stp", ".step"}:
        node = new_part(asm_path.stem)
        attach_cad_file(node, asm_path)
        return node

    node = new_assembly(asm_path.stem)
    attach_cad_file(node, asm_path)

    child_counts: Counter = Counter()
    if asm_path.suffix.lower() in {".stp", ".step", ".p21"}:
        step = parse_step_tree(asm_path)
        if step and step["kind"] == "part" and not step["children"]:
            part = new_part(step["name"])
            attach_cad_file(part, asm_path)
            return part
        if step:
            node["name"] = step["name"] or node["name"]
            child_counts = step["children"]
    else:
        child_counts = extract_referenced_names(asm_path)

    for raw_name, qty in child_counts.items():
        resolved = resolve_ref(raw_name, index, asm_path.parent)
        if resolved is None:
            base = Path(str(raw_name).replace("\\", "/")).name
            resolved = resolve_ref(base, index, asm_path.parent)
        if resolved is None:
            if "\\" in str(raw_name) or "/" in str(raw_name):
                continue
            _sys, ck = classify_cad_file(raw_name)
            child = new_assembly(Path(raw_name).stem) if ck == "assembly" else new_part(Path(raw_name).stem)
            child["qty"] = int(qty) if qty else 1
            child["notes"] = f"Файл не найден: {raw_name}"
            if ck == "assembly":
                node["assemblies"].append(child)
            else:
                node["parts"].append(child)
            continue
        _sys, ck = classify_cad_file(resolved)
        if ck == "assembly" or resolved.suffix.lower() in {".stp", ".step"}:
            child = _build_from_assembly(resolved, index, visited)
            if child.get("productType") == "Деталь" or "parts" not in child:
                child["qty"] = int(qty) if qty else 1
                node["parts"].append(child)
            else:
                child["qty"] = int(qty) if qty else 1
                node["assemblies"].append(child)
        elif ck == "drawing":
            continue
        else:
            part = new_part(resolved.stem)
            part["qty"] = int(qty) if qty else 1
            attach_cad_file(part, resolved)
            node["parts"].append(part)
    return node


def _folder_project(root: Path) -> dict:
    index = index_files(root)
    files = list_cad_files(root)
    assemblies = []
    parts = []
    drawings = []
    for p in files:
        _sys, kind = classify_cad_file(p)
        if kind == "assembly" or p.suffix.lower() in {".stp", ".step"}:
            assemblies.append(p)
        elif kind == "drawing":
            drawings.append(p)
        elif kind == "part":
            parts.append(p)

    referenced: set[str] = set()
    built = []
    for asm in assemblies:
        node = _ensure_assembly_node(_build_from_assembly(asm, index))
        built.append(node)
        referenced.add(str(asm.resolve()).lower())
        for name in extract_referenced_names(asm):
            resolved = resolve_ref(name, index, asm.parent)
            if resolved:
                referenced.add(str(resolved.resolve()).lower())
        step = parse_step_tree(asm) if asm.suffix.lower() in {".stp", ".step"} else None
        if step:
            referenced.add(str(asm.resolve()).lower())

    prj = new_project(root.name if root.is_dir() else root.stem)
    prj["notes"] = f"Выгружено из CAD: {root}"
    prj["folderPath"] = str(root if root.is_dir() else root.parent)
    prj["cadSource"] = str(root)

    top = []
    for node in built:
        path = (node.get("cadFiles") or {}).get("sw", {}).get("filePath") or node.get("filePath") or ""
        # сборка верхнего уровня — не является ребёнком другой
        is_child = False
        for other in built:
            if other is node:
                continue
            for child in other.get("assemblies") or []:
                if child.get("filePath") and child.get("filePath") == node.get("filePath"):
                    is_child = True
        if not is_child:
            top.append(node)
    if not top:
        top = built
    prj["assemblies"] = top

    orphans = []
    for p in parts:
        if str(p.resolve()).lower() in referenced:
            continue
        part = new_part(p.stem)
        attach_cad_file(part, p)
        orphans.append(part)
    if orphans:
        bucket = new_assembly("Прочие детали")
        bucket["parts"] = orphans
        bucket["notes"] = "Файлы, не входящие в разобранные сборки"
        prj["assemblies"].append(bucket)

    if drawings and not prj["assemblies"]:
        bucket = new_assembly("Чертежи")
        for p in drawings:
            part = new_part(p.stem)
            part["productType"] = "Документация"
            attach_cad_file(part, p)
            bucket["parts"].append(part)
        prj["assemblies"].append(bucket)

    if not prj["assemblies"] and parts:
        bucket = new_assembly(root.stem if root.is_file() else "Состав")
        for p in parts:
            part = new_part(p.stem)
            attach_cad_file(part, p)
            bucket["parts"].append(part)
        prj["assemblies"].append(bucket)

    return prj


def import_cad_source(source: str | Path, system_id: str | None = None) -> dict:
    """Импортировать файл или папку. Возвращает проект."""
    path = Path(source)
    if not path.exists():
        raise FileNotFoundError(path)
    from .teamcenter import import_teamcenter, looks_like_teamcenter

    if system_id == "teamcenter" or looks_like_teamcenter(path):
        return import_teamcenter(path)
    return _folder_project(path)


def import_from_running_cad(system_id: str) -> dict:
    path = active_document_path(system_id)
    if path is not None:
        return import_cad_source(path, system_id)
    if system_id == "nx" and (nx_looks_managed() or teamcenter_running()):
        raise GrabError(
            system_id,
            "NX открыт через Teamcenter, локального файла сборки нет. "
            "Выгрузите PLMXML из Teamcenter или укажите сохранённый .prt на диске.",
            managed=True,
        )
    names = {
        "nx": "Siemens NX",
        "solidworks": "SolidWorks",
        "kompas": "КОМПАС-3D",
        "inventor": "Inventor",
        "autocad": "AutoCAD",
    }
    title = names.get(system_id, "CAD")
    raise GrabError(
        system_id,
        f"{title} запущен, но сохранённый файл активного документа не найден. "
        "Сохраните сборку на диск или укажите файл вручную.",
        managed=False,
    )


def resync_link(project: dict) -> dict:
    """Повторно прочитать исходную папку/файл и вернуть новый проект (вызывающий мержит)."""
    source = project.get("cadSource") or project.get("folderPath")
    if not source:
        raise RuntimeError("У проекта нет связанного CAD-источника.")
    path = Path(source)
    if not path.exists():
        raise FileNotFoundError(source)
    fresh = import_cad_source(path)
    fresh["id"] = project.get("id") or fresh["id"]
    return fresh


def open_in_cad(path: str | Path) -> None:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(p)
    os.startfile(str(p))  # type: ignore[attr-defined]


def reveal_in_explorer(path: str | Path) -> None:
    p = Path(path)
    if p.is_dir():
        os.startfile(str(p))  # type: ignore[attr-defined]
        return
    if not p.exists():
        raise FileNotFoundError(p)
    subprocess.Popen(["explorer", "/select,", str(p)], creationflags=CREATE_NO_WINDOW)


def new_cad_link(system_id: str, source: str, project_id: str) -> dict:
    return {
        "id": uid("cad"),
        "system": system_id,
        "sourcePath": source,
        "projectId": project_id,
        "lastSync": "",
    }
