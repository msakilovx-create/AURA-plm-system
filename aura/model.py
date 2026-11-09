"""Модель документа AURA PLM: проект → сборка → деталь."""

from __future__ import annotations

import copy
import time
import uuid
from typing import Any, Optional

PRODUCT_TYPES = [
    "Деталь",
    "Сборочная единица",
    "Комплекс",
    "Комплект",
    "Покупное",
    "Стандартное",
    "Нормализованное",
    "Оригинальное",
    "Заимствованное",
    "Материал",
    "Документация",
]

STATUS_CYCLE = ("pending", "pass", "fail", "na")
STATUS_LABELS = {
    "pending": "Не проверено",
    "pass": "Соответствует",
    "fail": "Замечание",
    "na": "Не применимо",
}
STATUS_MARKS = {
    "pending": "?",
    "pass": "✓",
    "fail": "✕",
    "na": "–",
}


def uid(prefix: str) -> str:
    return f"{prefix}_{int(time.time() * 1000):x}_{uuid.uuid4().hex[:6]}"


def new_item(text: str) -> dict:
    return {"id": uid("itm"), "text": text, "status": "pending", "comment": ""}


def new_category(title: str, texts: list[str]) -> dict:
    return {"id": uid("cat"), "title": title, "items": [new_item(t) for t in texts]}


def new_worker() -> dict:
    return {"id": uid("w"), "name": "", "role": "", "pay": 0, "time": "", "nick": ""}


def new_part(name: str = "Новая деталь") -> dict:
    from .checklists import default_part_checklist

    return {
        "id": uid("part"),
        "name": name or "Новая деталь",
        "designation": "",
        "productType": "Деталь",
        "material": "",
        "coating": "",
        "revision": "",
        "drawnBy": "",
        "checkedBy": "",
        "date": "",
        "notes": "",
        "photo": "",
        "folderPath": "",
        "filePath": "",
        "cadFiles": empty_cad_files(),
        "navOrder": int(time.time() * 1000),
        "specPos": 0,
        "qty": 1,
        "cost": 0,
        "workers": [new_worker()],
        "checklist": default_part_checklist(),
    }


def new_assembly(name: str = "Новая сборка") -> dict:
    from .checklists import default_assembly_checklist

    return {
        "id": uid("asm"),
        "name": name or "Новая сборка",
        "designation": "",
        "productType": "Сборочная единица",
        "notes": "",
        "photo": "",
        "folderPath": "",
        "filePath": "",
        "cadFiles": empty_cad_files(),
        "expanded": True,
        "assemblies": [],
        "parts": [],
        "navOrder": int(time.time() * 1000),
        "specPos": 0,
        "qty": 1,
        "cost": 0,
        "workers": [new_worker()],
        "checklist": default_assembly_checklist(),
    }


def new_project(name: str = "Новый проект") -> dict:
    from .checklists import default_project_checklist

    return {
        "id": uid("prj"),
        "name": name or "Новый проект",
        "code": "",
        "notes": "",
        "folderPath": "",
        "cadSource": "",
        "expanded": True,
        "assemblies": [],
        "cost": 0,
        "checklist": default_project_checklist(),
    }


def empty_cad_slot() -> dict:
    return {"folderPath": "", "filePath": ""}


def empty_cad_files() -> dict:
    return {
        "sw": empty_cad_slot(),
        "stp": empty_cad_slot(),
        "pdf": empty_cad_slot(),
        "native": empty_cad_slot(),
        "extra": [],
    }


def ensure_cad_files(owner: dict) -> dict:
    if not owner:
        return empty_cad_files()
    cf = owner.get("cadFiles")
    if not isinstance(cf, dict):
        cf = empty_cad_files()
        if owner.get("filePath") or owner.get("folderPath"):
            cf["sw"]["filePath"] = owner.get("filePath") or ""
            cf["sw"]["folderPath"] = owner.get("folderPath") or ""
            cf["native"]["filePath"] = owner.get("filePath") or ""
            cf["native"]["folderPath"] = owner.get("folderPath") or ""
        owner["cadFiles"] = cf
        return cf
    for key in ("sw", "stp", "pdf", "native"):
        slot = cf.get(key)
        if not isinstance(slot, dict):
            cf[key] = empty_cad_slot()
        else:
            slot.setdefault("folderPath", "")
            slot.setdefault("filePath", "")
    if not isinstance(cf.get("extra"), list):
        cf["extra"] = []
    if not (cf["sw"].get("filePath") or "").strip() and (owner.get("filePath") or "").strip():
        cf["sw"]["filePath"] = owner.get("filePath") or ""
        cf["sw"]["folderPath"] = owner.get("folderPath") or ""
    owner["cadFiles"] = cf
    return cf


def empty_cad_state() -> dict:
    return {"links": []}


def empty_library() -> dict:
    return {
        "workers": [],
        "materials": [],
        "productTypes": PRODUCT_TYPES[:],
        "standards": [],
        "coatings": [],
    }


def empty_document() -> dict:
    return {
        "app": "AURA PLM System",
        "version": 1,
        "projects": [],
        "selection": {
            "type": None,
            "projectId": None,
            "assemblyId": None,
            "partId": None,
        },
        "cart": [],
        "library": empty_library(),
        "cad": empty_cad_state(),
        "vault": {"root": ""},
        "owner": "",
    }


def seed_document() -> dict:
    part1 = new_part("Деталь 1")
    part2 = new_part("Деталь 2")
    asm1 = new_assembly("Сборка 1")
    asm1["parts"].extend([part1, part2])
    prj1 = new_project("Проект 1")
    prj1["assemblies"].append(asm1)

    part3 = new_part("Деталь 1")
    asm2 = new_assembly("Сборка 1")
    asm2["parts"].append(part3)
    prj2 = new_project("Проект 2")
    prj2["assemblies"].append(asm2)

    doc = empty_document()
    doc["projects"] = [prj1, prj2]
    doc["selection"] = {
        "type": "part",
        "projectId": prj1["id"],
        "assemblyId": asm1["id"],
        "partId": part1["id"],
    }
    return doc


def find_project(doc: dict, project_id: str) -> Optional[dict]:
    for p in doc.get("projects") or []:
        if p.get("id") == project_id:
            return p
    return None


def find_assembly_in_list(assemblies: list, assembly_id: str) -> Optional[dict]:
    for a in assemblies or []:
        if a.get("id") == assembly_id:
            return a
        found = find_assembly_in_list(a.get("assemblies") or [], assembly_id)
        if found:
            return found
    return None


def find_assembly(doc: dict, project_id: str, assembly_id: str) -> Optional[dict]:
    prj = find_project(doc, project_id)
    if not prj:
        return None
    return find_assembly_in_list(prj.get("assemblies") or [], assembly_id)


def find_part_in_assembly(asm: dict, part_id: str) -> Optional[dict]:
    if not asm:
        return None
    for p in asm.get("parts") or []:
        if p.get("id") == part_id:
            return p
    for nested in asm.get("assemblies") or []:
        found = find_part_in_assembly(nested, part_id)
        if found:
            return found
    return None


def parent_of_assembly(prj: dict, assembly_id: str):
    """Вернуть (parent_node, list_name) где лежит сборка. parent_node — проект или сборка."""

    def walk(node, list_name):
        items = node.get(list_name) or []
        for a in items:
            if a.get("id") == assembly_id:
                return node, list_name
            found = walk(a, "assemblies")
            if found:
                return found
        return None

    return walk(prj, "assemblies")


def parent_of_part(prj: dict, part_id: str) -> Optional[dict]:
    def walk(asm):
        for p in asm.get("parts") or []:
            if p.get("id") == part_id:
                return asm
        for nested in asm.get("assemblies") or []:
            found = walk(nested)
            if found:
                return found
        return None

    for a in prj.get("assemblies") or []:
        found = walk(a)
        if found:
            return found
    return None


def delete_node(doc: dict, kind: str, project_id: str, assembly_id: str | None, part_id: str | None) -> bool:
    if kind == "project":
        before = len(doc.get("projects") or [])
        doc["projects"] = [p for p in doc.get("projects") or [] if p.get("id") != project_id]
        return len(doc["projects"]) != before

    prj = find_project(doc, project_id)
    if not prj:
        return False

    if kind == "assembly" and assembly_id:
        loc = parent_of_assembly(prj, assembly_id)
        if not loc:
            return False
        parent, list_name = loc
        parent[list_name] = [a for a in parent.get(list_name) or [] if a.get("id") != assembly_id]
        return True

    if kind == "part" and part_id:
        parent = parent_of_part(prj, part_id)
        if not parent:
            return False
        parent["parts"] = [p for p in parent.get("parts") or [] if p.get("id") != part_id]
        return True
    return False


def _refresh_ids(node: dict, kind: str) -> dict:
    node = copy.deepcopy(node)
    if kind == "project":
        node["id"] = uid("prj")
        node["assemblies"] = [_refresh_ids(a, "assembly") for a in node.get("assemblies") or []]
        _refresh_checklist_ids(node)
    elif kind == "assembly":
        node["id"] = uid("asm")
        node["assemblies"] = [_refresh_ids(a, "assembly") for a in node.get("assemblies") or []]
        node["parts"] = [_refresh_ids(p, "part") for p in node.get("parts") or []]
        _refresh_checklist_ids(node)
        for w in node.get("workers") or []:
            w["id"] = uid("w")
    else:
        node["id"] = uid("part")
        _refresh_checklist_ids(node)
        for w in node.get("workers") or []:
            w["id"] = uid("w")
    return node


def _refresh_checklist_ids(node: dict) -> None:
    for cat in node.get("checklist") or []:
        cat["id"] = uid("cat")
        for it in cat.get("items") or []:
            it["id"] = uid("itm")


def duplicate_node(node: dict, kind: str) -> dict:
    clone = _refresh_ids(node, kind)
    name = str(clone.get("name") or "")
    clone["name"] = (name + " (копия)").strip()
    return clone


def qty_of(node: dict) -> float:
    try:
        q = float(node.get("qty") or 1)
    except (TypeError, ValueError):
        q = 1
    return q if q > 0 else 1


def is_auto_cost_type(product_type: str) -> bool:
    t = str(product_type or "").strip().lower()
    return t == "сборочная единица" or "сборочн" in t


def workers_pay_sum(node: dict) -> float:
    total = 0.0
    for w in node.get("workers") or []:
        try:
            total += float(w.get("pay") or 0)
        except (TypeError, ValueError):
            pass
    return total


def node_material_cost(node: dict, kind: str) -> float:
    if not node:
        return 0.0
    if kind == "part":
        try:
            return float(node.get("cost") or 0)
        except (TypeError, ValueError):
            return 0.0
    if is_auto_cost_type(node.get("productType")):
        total = 0.0
        for p in node.get("parts") or []:
            total += node_material_cost(p, "part") * qty_of(p)
        for a in node.get("assemblies") or []:
            total += node_material_cost(a, "assembly") * qty_of(a)
        return total
    try:
        return float(node.get("cost") or 0)
    except (TypeError, ValueError):
        return 0.0


def node_labor_cost(node: dict, kind: str) -> float:
    if not node:
        return 0.0
    total = workers_pay_sum(node)
    if kind == "part":
        return total
    for p in node.get("parts") or []:
        total += workers_pay_sum(p)
    for a in node.get("assemblies") or []:
        total += node_labor_cost(a, "assembly") * qty_of(a)
    return total


def node_unit_cost(node: dict, kind: str) -> float:
    return node_material_cost(node, kind) + node_labor_cost(node, kind)


def project_material_cost(prj: dict) -> float:
    total = 0.0
    for a in prj.get("assemblies") or []:
        total += node_material_cost(a, "assembly") * qty_of(a)
    return total


def project_labor_cost(prj: dict) -> float:
    total = 0.0
    for a in prj.get("assemblies") or []:
        total += node_labor_cost(a, "assembly") * qty_of(a)
    return total


def project_total_cost(prj: dict) -> float:
    return project_material_cost(prj) + project_labor_cost(prj)


def format_money(value: Any) -> str:
    try:
        n = float(value or 0)
    except (TypeError, ValueError):
        n = 0.0
    text = f"{n:,.2f}"
    return text.replace(",", " ").replace(".", ",")


def checklist_stats(checklist: list) -> dict:
    stats = {"total": 0, "pass": 0, "fail": 0, "na": 0, "pending": 0}
    for cat in checklist or []:
        for it in cat.get("items") or []:
            stats["total"] += 1
            st = it.get("status") or "pending"
            if st in stats:
                stats[st] += 1
            else:
                stats["pending"] += 1
    return stats


def walk_checklists(node: dict, kind: str) -> dict:
    stats = checklist_stats(node.get("checklist") or [])
    if kind == "part":
        return stats
    for p in node.get("parts") or []:
        stats = _add_stats(stats, walk_checklists(p, "part"))
    for a in node.get("assemblies") or []:
        stats = _add_stats(stats, walk_checklists(a, "assembly"))
    return stats


def _add_stats(a: dict, b: dict) -> dict:
    return {k: a.get(k, 0) + b.get(k, 0) for k in ("total", "pass", "fail", "na", "pending")}


def next_status(current: str) -> str:
    cur = current if current in STATUS_CYCLE else "pending"
    return STATUS_CYCLE[(STATUS_CYCLE.index(cur) + 1) % len(STATUS_CYCLE)]


def node_matches(node: dict, query: str) -> bool:
    if not query:
        return True
    q = query.casefold()
    fields = [
        node.get("name"),
        node.get("code"),
        node.get("designation"),
        node.get("material"),
        node.get("notes"),
    ]
    return any(q in str(v or "").casefold() for v in fields)


def assembly_matches(asm: dict, query: str) -> bool:
    if node_matches(asm, query):
        return True
    for p in asm.get("parts") or []:
        if node_matches(p, query):
            return True
    for nested in asm.get("assemblies") or []:
        if assembly_matches(nested, query):
            return True
    return False


def project_matches(prj: dict, query: str) -> bool:
    if node_matches(prj, query):
        return True
    for a in prj.get("assemblies") or []:
        if assembly_matches(a, query):
            return True
    return False


def materials_from_library(doc: dict) -> list[str]:
    names = []
    for m in (doc.get("library") or {}).get("materials") or []:
        if isinstance(m, str):
            if m.strip():
                names.append(m.strip())
        elif isinstance(m, dict) and m.get("name"):
            names.append(str(m["name"]).strip())
    seen = set()
    out = []
    for n in names:
        key = n.casefold()
        if key not in seen:
            seen.add(key)
            out.append(n)
    return sorted(out, key=lambda s: s.casefold())


def product_types(doc: dict) -> list[str]:
    types = list((doc.get("library") or {}).get("productTypes") or [])
    if not types:
        types = PRODUCT_TYPES[:]
    out = []
    seen = set()
    for t in types:
        s = str(t).strip()
        if s and s.casefold() not in seen:
            seen.add(s.casefold())
            out.append(s)
    return out


def tree_label(kind: str, node: dict) -> str:
    name = str(node.get("name") or "без имени")
    extra = node.get("code") if kind == "project" else node.get("designation")
    if extra:
        return f"{name}  [{extra}]"
    return name
