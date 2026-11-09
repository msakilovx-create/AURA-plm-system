"""Корзина покупнины — те же правила, что в HTML-менеджере проектов."""

from __future__ import annotations

from .model import find_assembly, find_part_in_assembly, is_auto_cost_type, qty_of, uid


def cart_count(doc: dict) -> int:
    return sum(int(c.get("qty") or 1) for c in doc.get("cart") or [])


def cart_line_total(item: dict) -> float:
    try:
        return float(item.get("unitCost") or 0) * float(item.get("qty") or 1)
    except (TypeError, ValueError):
        return 0.0


def cart_grand_total(doc: dict) -> float:
    return sum(cart_line_total(c) for c in doc.get("cart") or [])


def find_cart_item(doc: dict, kind: str, node_id: str):
    for c in doc.get("cart") or []:
        if c.get("kind") == kind and c.get("nodeId") == node_id:
            return c
    return None


def is_in_cart(doc: dict, kind: str, node_id: str) -> bool:
    return find_cart_item(doc, kind, node_id) is not None


def push_cart_item(doc: dict, entry: dict) -> dict:
    doc.setdefault("cart", [])
    unit = float(entry.get("unitCost") or 0)
    item = find_cart_item(doc, entry.get("kind"), entry.get("nodeId"))
    if item:
        item["qty"] = int(item.get("qty") or 1) + int(entry.get("qty") or 1)
        for k in ("name", "designation", "productType", "material", "folderPath", "filePath", "photo"):
            if entry.get(k) is not None:
                item[k] = entry.get(k)
        item["unitCost"] = unit
        return item
    row = {
        "id": uid("cart"),
        "kind": entry.get("kind"),
        "nodeId": entry.get("nodeId"),
        "projectId": entry.get("projectId"),
        "assemblyId": entry.get("assemblyId"),
        "partId": entry.get("partId"),
        "name": entry.get("name") or "",
        "designation": entry.get("designation") or "",
        "productType": entry.get("productType") or "",
        "material": entry.get("material") or "",
        "folderPath": entry.get("folderPath") or "",
        "filePath": entry.get("filePath") or "",
        "photo": entry.get("photo") or "",
        "qty": int(entry.get("qty") or 1),
        "unitCost": unit,
        "note": "",
    }
    doc["cart"].append(row)
    return row


def collect_assembly_cart_entries(asm: dict, project_id: str, parent_asm_id: str | None, mult: float) -> list:
    mult = mult if mult and mult > 0 else 1
    out = []
    if not asm:
        return out
    for p in asm.get("parts") or []:
        q = qty_of(p) * mult
        out.append({
            "kind": "part",
            "nodeId": p.get("id"),
            "projectId": project_id,
            "assemblyId": parent_asm_id or asm.get("id"),
            "partId": p.get("id"),
            "name": p.get("name"),
            "designation": p.get("designation") or "",
            "productType": p.get("productType") or "Деталь",
            "material": p.get("material") or "",
            "folderPath": p.get("folderPath") or "",
            "filePath": p.get("filePath") or "",
            "photo": p.get("photo") or "",
            "qty": q,
            "unitCost": float(p.get("cost") or 0),
        })
    for sub in asm.get("assemblies") or []:
        q = qty_of(sub) * mult
        if is_auto_cost_type(sub.get("productType")):
            out.extend(collect_assembly_cart_entries(sub, project_id, sub.get("id"), q))
        else:
            out.append({
                "kind": "assembly",
                "nodeId": sub.get("id"),
                "projectId": project_id,
                "assemblyId": sub.get("id"),
                "partId": None,
                "name": sub.get("name"),
                "designation": sub.get("designation") or "",
                "productType": sub.get("productType") or "Сборочная единица",
                "material": "",
                "folderPath": sub.get("folderPath") or "",
                "filePath": sub.get("filePath") or "",
                "photo": sub.get("photo") or "",
                "qty": q,
                "unitCost": float(sub.get("cost") or 0),
            })
    return out


def add_node_to_cart(doc: dict, kind: str, project_id: str, assembly_id: str | None, part_id: str | None, qty: int = 1) -> str:
    qty = max(1, int(qty or 1))
    if kind == "part":
        asm = find_assembly(doc, project_id, assembly_id)
        part = find_part_in_assembly(asm, part_id) if asm else None
        if not part:
            raise ValueError("Деталь не найдена.")
        push_cart_item(doc, {
            "kind": "part",
            "nodeId": part["id"],
            "projectId": project_id,
            "assemblyId": assembly_id,
            "partId": part["id"],
            "name": part.get("name"),
            "designation": part.get("designation") or "",
            "productType": part.get("productType") or "Деталь",
            "material": part.get("material") or "",
            "folderPath": part.get("folderPath") or "",
            "filePath": part.get("filePath") or "",
            "photo": part.get("photo") or "",
            "qty": qty,
            "unitCost": float(part.get("cost") or 0),
        })
        return f"В корзину: «{part.get('name')}» ×{qty}"
    asm = find_assembly(doc, project_id, assembly_id)
    if not asm:
        raise ValueError("Сборка не найдена.")
    if is_auto_cost_type(asm.get("productType")):
        entries = collect_assembly_cart_entries(asm, project_id, asm["id"], qty)
        if not entries:
            raise ValueError("В сборке нет элементов для корзины.")
        for e in entries:
            push_cart_item(doc, e)
        return f"В корзину состав «{asm.get('name')}»: {len(entries)} поз."
    push_cart_item(doc, {
        "kind": "assembly",
        "nodeId": asm["id"],
        "projectId": project_id,
        "assemblyId": asm["id"],
        "partId": None,
        "name": asm.get("name"),
        "designation": asm.get("designation") or "",
        "productType": asm.get("productType") or "Сборочная единица",
        "material": "",
        "folderPath": asm.get("folderPath") or "",
        "filePath": asm.get("filePath") or "",
        "photo": asm.get("photo") or "",
        "qty": qty,
        "unitCost": float(asm.get("cost") or 0),
    })
    return f"В корзину: «{asm.get('name')}» ×{qty}"


def update_cart_qty(doc: dict, cart_id: str, qty) -> None:
    for c in doc.get("cart") or []:
        if c.get("id") == cart_id:
            c["qty"] = max(1, int(float(qty or 1)))
            return


def update_cart_note(doc: dict, cart_id: str, note: str) -> None:
    for c in doc.get("cart") or []:
        if c.get("id") == cart_id:
            c["note"] = note
            return


def remove_from_cart(doc: dict, cart_id: str) -> None:
    doc["cart"] = [c for c in (doc.get("cart") or []) if c.get("id") != cart_id]


def clear_cart(doc: dict) -> None:
    doc["cart"] = []


def build_hierarchy_rows(prj: dict) -> list:
    rows = [{
        "level": 0,
        "name": prj.get("name") or "",
        "designation": prj.get("code") or "",
        "type": "Комплекс / Проект",
        "parent": "",
        "photo": prj.get("photo") or "",
    }]

    def walk_asm(asm, level, parent_des):
        rows.append({
            "level": level,
            "name": asm.get("name") or "",
            "designation": asm.get("designation") or "",
            "type": asm.get("productType") or "Сборочная единица",
            "parent": parent_des or "",
            "photo": asm.get("photo") or "",
        })
        self_des = asm.get("designation") or asm.get("name") or ""
        for sub in asm.get("assemblies") or []:
            walk_asm(sub, level + 1, self_des)
        for p in asm.get("parts") or []:
            rows.append({
                "level": level + 1,
                "name": p.get("name") or "",
                "designation": p.get("designation") or "",
                "type": p.get("productType") or "Деталь",
                "parent": self_des,
                "photo": p.get("photo") or "",
            })

    project_des = prj.get("code") or prj.get("name") or ""
    for a in prj.get("assemblies") or []:
        walk_asm(a, 1, project_des)
    return rows
