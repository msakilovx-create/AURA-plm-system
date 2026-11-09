"""Выгрузка состава из Siemens Teamcenter: PLMXML, TcXML, briefcase, CSV BOM."""

from __future__ import annotations

import csv
import io
import os
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from ..model import new_assembly, new_part, new_project

TC_XML_HINTS = ("plmxml", "tcxml", "<productdef", "<productrevision", "<item ", "instancegraph")
BOM_HEADERS = {
    "level": ("level", "lvl", "уровень", "bom level", "indent"),
    "id": ("item id", "item_id", "itemid", "id", "обозначение", "шифр", "part number", "partnumber", "object_name_id"),
    "name": ("name", "наименование", "object_name", "description", "описание", "item name"),
    "rev": ("revision", "rev", "ревизия", "item_revision_id", "revision id"),
    "qty": ("qty", "quantity", "кол-во", "количество", "qty_value", "bl_quantity"),
    "type": ("type", "тип", "item type", "object_type", "item_type"),
    "parent": ("parent", "parent id", "родитель", "parent_id"),
}


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if tag else ""


def _attr(el: ET.Element, *names: str) -> str:
    for n in names:
        v = el.get(n)
        if v:
            return v
        for k, val in el.attrib.items():
            if _local(k).lower() == n.lower() and val:
                return val
    return ""


def _ref_id(value: str) -> str:
    return (value or "").lstrip("#").strip()


def looks_like_teamcenter(path: str | Path) -> bool:
    p = Path(path)
    if not p.exists():
        return False
    suf = p.suffix.lower()
    if suf in {".plmxml", ".bcz"}:
        return True
    if suf == ".zip":
        try:
            with zipfile.ZipFile(p) as zf:
                return any(n.lower().endswith((".plmxml", ".xml")) for n in zf.namelist())
        except Exception:
            return False
    if suf in {".xml", ".csv", ".tsv", ".txt"}:
        try:
            head = p.read_text(encoding="utf-8", errors="ignore")[:4000].lower()
        except OSError:
            return False
        if suf == ".xml" or suf == ".plmxml":
            return any(h in head for h in TC_XML_HINTS)
        return _csv_header_map(head.splitlines()[0] if head else "") is not None
    return False


def _csv_header_map(header_line: str) -> dict[str, int] | None:
    if not header_line:
        return None
    dialect_sample = header_line
    delim = ";" if dialect_sample.count(";") > dialect_sample.count(",") else ","
    if "\t" in dialect_sample and dialect_sample.count("\t") >= dialect_sample.count(delim):
        delim = "\t"
    cols = [c.strip().strip('"').lower() for c in header_line.split(delim)]
    mapping: dict[str, int] = {}
    for key, aliases in BOM_HEADERS.items():
        for i, col in enumerate(cols):
            if col in aliases:
                mapping[key] = i
                break
    if "name" in mapping or "id" in mapping:
        return mapping
    return None


def _user_values(el: ET.Element) -> dict[str, str]:
    out = {}
    for child in el.iter():
        if _local(child.tag) not in {"UserValue", "Attribute"}:
            continue
        title = (_attr(child, "title", "name") or "").strip()
        value = (_attr(child, "value") or (child.text or "")).strip()
        if title:
            out[title] = value
            out[title.lower()] = value
    return out


def _qty_of(el: ET.Element, values: dict[str, str] | None = None) -> int:
    values = values or _user_values(el)
    for key in ("Quantity", "quantity", "bl_quantity", "BL_QUANTITY", "qty_value", "Qty"):
        raw = values.get(key) or values.get(key.lower()) or _attr(el, key, "qty", "quantity")
        if raw:
            try:
                return max(1, int(float(str(raw).replace(",", "."))))
            except ValueError:
                continue
    return 1


def _by_id(root: ET.Element) -> dict[str, ET.Element]:
    found = {}
    for el in root.iter():
        eid = _attr(el, "id")
        if eid:
            found[eid] = el
            found[_ref_id(eid)] = el
    return found


def _product_info(el: ET.Element | None, by_id: dict[str, ET.Element]) -> dict:
    info = {"name": "", "designation": "", "revision": "", "item_type": "", "files": []}
    seen = set()
    cur = el
    while cur is not None:
        cid = id(cur)
        if cid in seen:
            break
        seen.add(cid)
        tag = _local(cur.tag)
        info["name"] = info["name"] or _attr(cur, "name") or _user_values(cur).get("object_name", "")
        info["revision"] = info["revision"] or _attr(cur, "revision", "item_revision_id")
        info["item_type"] = info["item_type"] or _attr(cur, "subType", "object_type", "type")
        info["designation"] = (
            info["designation"]
            or _attr(cur, "productId", "item_id")
            or _user_values(cur).get("item_id", "")
        )
        for child in list(cur)[:40]:
            if _local(child.tag) in {"ExternalFile", "Representation"}:
                loc = _attr(child, "locationRef", "location", "uri")
                if loc:
                    info["files"].append(loc)
        master = _ref_id(_attr(cur, "masterRef", "revisionRef", "instancedRef", "partRef"))
        cur = by_id.get(master) if master else None
        if tag in {"Product", "Item"}:
            break
    return info


def _child_instance_ids(el: ET.Element) -> list[str]:
    refs = _attr(el, "instanceRefs")
    ids = [_ref_id(x) for x in refs.split() if _ref_id(x)]
    for child in el:
        tag = _local(child.tag)
        if tag in {"ProductInstance", "Occurrence", "PSOccurrence"}:
            cid = _attr(child, "id")
            if cid:
                ids.append(cid)
            else:
                inst = _ref_id(_attr(child, "instancedRef", "instanceRef", "child_item"))
                if inst:
                    ids.append(inst)
        if tag in {"InstanceRefs"}:
            for ref in child:
                inst = _ref_id(_attr(ref, "instanceRef", "instancedRef") or (ref.text or ""))
                if inst:
                    ids.append(inst)
    return ids


def _root_instance_ids(root: ET.Element) -> list[str]:
    ids = []
    for el in root.iter():
        if _local(el.tag) == "InstanceGraph":
            rid = _ref_id(_attr(el, "rootInstanceRef"))
            if rid:
                ids.append(rid)
    if ids:
        return ids
    for el in root.iter():
        if _local(el.tag) == "ProductDef":
            for g in el:
                if _local(g.tag) == "InstanceGraph":
                    for inst in g:
                        if _local(inst.tag) == "ProductInstance" and _attr(inst, "id"):
                            ids.append(_attr(inst, "id"))
                            break
    return [x for x in ids if x]


def _is_assembly_type(item_type: str, has_children: bool) -> bool:
    if has_children:
        return True
    t = (item_type or "").lower()
    return any(x in t for x in ("assembl", "сборк"))


def _attach_files(node: dict, files: list[str], folder: Path) -> None:
    from .importing import attach_cad_file

    for loc in files:
        loc = loc.replace("file:///", "").replace("file://", "")
        cand = Path(loc)
        if not cand.is_absolute():
            cand = folder / loc
        if cand.exists() and cand.is_file():
            attach_cad_file(node, cand)
            return


def _build_node(el: ET.Element, by_id: dict[str, ET.Element], folder: Path, visiting: set[str]) -> dict:
    eid = _attr(el, "id") or str(id(el))
    if eid in visiting:
        info = _product_info(el, by_id)
        part = new_part(info["name"] or eid)
        part["productType"] = "Заимствованное"
        return part
    visiting.add(eid)

    instanced = _ref_id(_attr(el, "instancedRef", "revisionRef", "partRef", "masterRef"))
    target = by_id.get(instanced, el)
    info = _product_info(target, by_id)
    if not info["name"]:
        info["name"] = _attr(el, "name") or info["designation"] or eid
    qty = _qty_of(el)

    child_ids = _child_instance_ids(el)
    if not child_ids:
        child_ids = _child_instance_ids(target)
    children = []
    for cid in child_ids:
        child_el = by_id.get(cid)
        if child_el is None:
            continue
        children.append(_build_node(child_el, by_id, folder, visiting))

    if children or _is_assembly_type(info["item_type"], False):
        node = new_assembly(info["name"])
        for ch in children:
            if "assemblies" in ch and "parts" in ch:
                node["assemblies"].append(ch)
            else:
                node["parts"].append(ch)
    else:
        node = new_part(info["name"])
    node["designation"] = info["designation"]
    node["revision"] = info["revision"]
    node["qty"] = qty
    if info["item_type"]:
        low = info["item_type"].lower()
        if "assembl" in low or "сборк" in low:
            node["productType"] = "Сборочная единица"
        elif "part" in low or "детал" in low:
            node["productType"] = "Деталь"
    if info["designation"] or info["revision"]:
        extra = "Teamcenter"
        if info["designation"]:
            extra += f" {info['designation']}"
        if info["revision"]:
            extra += f" rev.{info['revision']}"
        node["notes"] = extra
    _attach_files(node, info["files"], folder)
    visiting.discard(eid)
    return node


def _parse_plmxml_root(root: ET.Element, folder: Path, source_name: str) -> dict:
    by_id = _by_id(root)
    roots = _root_instance_ids(root)
    nodes = []
    visiting: set[str] = set()
    for rid in roots:
        el = by_id.get(rid)
        if el is None:
            continue
        nodes.append(_build_node(el, by_id, folder, visiting))
    if not nodes:
        revs = [el for el in root.iter() if _local(el.tag) == "ProductRevision"]
        if revs:
            nodes.append(_build_node(revs[0], by_id, folder, visiting))
    if not nodes:
        raise ValueError("В файле Teamcenter нет состава изделия (InstanceGraph / ProductRevision).")

    top = nodes[0]
    if "assemblies" not in top:
        wrap = new_assembly(top.get("name") or source_name)
        wrap["parts"] = [top]
        wrap["designation"] = top.get("designation") or ""
        top = wrap
    prj = new_project(top.get("name") or source_name)
    prj["code"] = top.get("designation") or ""
    prj["notes"] = f"Выгружено из Teamcenter: {source_name}"
    prj["cadSource"] = str(folder / source_name) if source_name else str(folder)
    prj["folderPath"] = str(folder)
    prj["assemblies"] = [top] + nodes[1:]
    return prj


def _parse_tcxml(root: ET.Element, folder: Path, source_name: str) -> dict:
    """Упрощённый TcXML: Item / ItemRevision / PSOccurrence."""
    items = {}
    for el in root.iter():
        if _local(el.tag) not in {"Item", "item"}:
            continue
        iid = _attr(el, "item_id", "id")
        name = _attr(el, "object_name", "name") or iid
        if iid:
            items[iid] = {"name": name, "type": _attr(el, "object_type", "type"), "el": el}

    occs = []
    for el in root.iter():
        if _local(el.tag) not in {"PSOccurrence", "Occurrence"}:
            continue
        child = _attr(el, "child_item", "childItem", "instancedRef")
        parent = _attr(el, "parent_item", "parentItem")
        qty = _qty_of(el)
        occs.append((parent, _ref_id(child), qty))

    if not items and not occs:
        raise ValueError("Файл не похож на PLMXML или TcXML Teamcenter.")

    children_of: dict[str, list] = {}
    child_ids = set()
    for parent, child, qty in occs:
        if not child:
            continue
        children_of.setdefault(parent or "", []).append((child, qty))
        child_ids.add(child)
    roots = [iid for iid in items if iid not in child_ids] or list(items.keys())[:1]

    def make(iid: str, qty: int) -> dict:
        meta = items.get(iid, {"name": iid, "type": ""})
        kids = children_of.get(iid) or children_of.get("#" + iid) or []
        if kids:
            node = new_assembly(meta["name"] or iid)
            for cid, cq in kids:
                ch = make(cid, cq)
                if "assemblies" in ch and "parts" in ch:
                    node["assemblies"].append(ch)
                else:
                    node["parts"].append(ch)
        else:
            node = new_part(meta["name"] or iid)
        node["designation"] = iid
        node["qty"] = qty
        node["notes"] = f"Teamcenter {iid}"
        return node

    prj = new_project(items[roots[0]]["name"] if roots and roots[0] in items else source_name)
    prj["notes"] = f"Выгружено из Teamcenter: {source_name}"
    prj["folderPath"] = str(folder)
    for rid in roots:
        node = make(rid, 1)
        if "assemblies" not in node:
            wrap = new_assembly(node.get("name") or rid)
            wrap["parts"] = [node]
            node = wrap
        prj["assemblies"].append(node)
    return prj


def parse_teamcenter_xml(text: str, folder: Path, source_name: str) -> dict:
    root = ET.fromstring(text)
    tags = {_local(el.tag).lower() for el in root.iter()}
    if "instancegraph" in tags or "productrevision" in tags or "productdef" in tags or _local(root.tag).lower() == "plmxml":
        return _parse_plmxml_root(root, folder, source_name)
    return _parse_tcxml(root, folder, source_name)


def parse_teamcenter_csv(text: str, folder: Path, source_name: str) -> dict:
    sample = text.splitlines()[0] if text else ""
    mapping = _csv_header_map(sample)
    if mapping is None:
        raise ValueError("CSV не похож на ведомость Teamcenter (нет колонок имени или обозначения).")
    delim = ";" if sample.count(";") > sample.count(",") else ","
    if "\t" in sample and sample.count("\t") >= sample.count(delim):
        delim = "\t"
    reader = csv.reader(io.StringIO(text), delimiter=delim)
    rows = list(reader)
    if not rows:
        raise ValueError("Пустой CSV.")
    data = rows[1:]
    last_at: dict[int, dict] = {}
    roots: list[dict] = []

    def cell(row, key, default=""):
        i = mapping.get(key)
        if i is None or i >= len(row):
            return default
        return (row[i] or "").strip()

    def promote(node: dict) -> dict:
        if "assemblies" in node and "parts" in node:
            return node
        node.setdefault("assemblies", [])
        node.setdefault("parts", [])
        node["productType"] = "Сборочная единица"
        node["expanded"] = True
        return node

    for row in data:
        if not any((x or "").strip() for x in row):
            continue
        name = cell(row, "name") or cell(row, "id") or "Элемент"
        des = cell(row, "id")
        rev = cell(row, "rev")
        typ = cell(row, "type")
        try:
            qty = max(1, int(float(cell(row, "qty", "1").replace(",", ".") or 1)))
        except ValueError:
            qty = 1
        try:
            level = int(float(cell(row, "level", "1") or 1))
        except ValueError:
            level = 1
        node = new_assembly(name) if _is_assembly_type(typ, False) else new_part(name)
        node["designation"] = des
        node["revision"] = rev
        node["qty"] = qty
        node["notes"] = f"Teamcenter {des}".strip()
        for lv in [k for k in last_at if k >= level]:
            del last_at[lv]
        parent = None
        for lv in range(level - 1, 0, -1):
            if lv in last_at:
                parent = last_at[lv]
                break
        if parent is None:
            node = promote(node)
            roots.append(node)
            last_at[level] = node
        else:
            parent = promote(parent)
            parent.setdefault("assemblies", [])
            parent.setdefault("parts", [])
            if "assemblies" in node and "parts" in node:
                parent["assemblies"].append(node)
            else:
                parent["parts"].append(node)
            last_at[level] = node

    if not roots:
        raise ValueError("В CSV нет строк состава.")
    prj = new_project(roots[0].get("name") or source_name)
    prj["code"] = roots[0].get("designation") or ""
    prj["notes"] = f"Выгружено из Teamcenter (CSV): {source_name}"
    prj["folderPath"] = str(folder)
    prj["assemblies"] = roots
    return prj


def _xml_from_zip(path: Path) -> tuple[str, Path]:
    with zipfile.ZipFile(path) as zf:
        names = [n for n in zf.namelist() if n.lower().endswith((".plmxml", ".xml")) and not n.endswith("/")]
        if not names:
            raise ValueError("В архиве Teamcenter нет PLMXML.")
        preferred = [n for n in names if n.lower().endswith(".plmxml")] or names
        name = preferred[0]
        text = zf.read(name).decode("utf-8", errors="ignore")
        return text, path.parent


def import_teamcenter(path: str | Path) -> dict:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(p)
    if p.is_dir():
        cands = list(p.glob("*.plmxml")) + list(p.glob("*.xml")) + list(p.glob("*.csv")) + list(p.glob("*.bcz"))
        if not cands:
            raise FileNotFoundError("В папке нет PLMXML / CSV Teamcenter.")
        p = cands[0]
    folder = p.parent
    suf = p.suffix.lower()
    if suf in {".zip", ".bcz"}:
        text, folder = _xml_from_zip(p)
        prj = parse_teamcenter_xml(text, folder, p.name)
    elif suf in {".csv", ".tsv", ".txt"}:
        text = p.read_text(encoding="utf-8-sig", errors="ignore")
        prj = parse_teamcenter_csv(text, folder, p.name)
    else:
        text = p.read_text(encoding="utf-8-sig", errors="ignore")
        prj = parse_teamcenter_xml(text, folder, p.name)
    prj["cadSource"] = str(p)
    prj["folderPath"] = str(folder)
    return prj


def find_recent_teamcenter_exports(limit: int = 12) -> list[Path]:
    roots = []
    for env in ("USERPROFILE", "TEMP", "TMP", "TC_TMP_DIR", "TC_DATA"):
        v = os.environ.get(env)
        if v:
            roots.append(Path(v))
    home = Path(os.environ.get("USERPROFILE", str(Path.home())))
    roots.extend([home / "Desktop", home / "Documents", home / "Downloads"])
    found: list[Path] = []
    seen = set()
    for root in roots:
        if not root.exists():
            continue
        try:
            for p in root.iterdir():
                if not p.is_file():
                    continue
                if p.suffix.lower() not in {".plmxml", ".bcz", ".xml", ".csv"}:
                    continue
                if p.suffix.lower() in {".xml", ".csv"} and not looks_like_teamcenter(p):
                    continue
                key = str(p.resolve()).lower()
                if key in seen:
                    continue
                seen.add(key)
                found.append(p)
        except OSError:
            continue
    found.sort(key=lambda x: x.stat().st_mtime if x.exists() else 0, reverse=True)
    return found[:limit]


TC_FILE_FILTER = [
    ("Teamcenter PLMXML", "*.plmxml;*.xml;*.bcz;*.zip"),
    ("Ведомость CSV", "*.csv;*.tsv;*.txt"),
    ("Все файлы", "*.*"),
]
