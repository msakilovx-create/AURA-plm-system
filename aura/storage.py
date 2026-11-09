"""Открытие и сохранение JSON-документов AURA PLM."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .model import empty_document, empty_library, new_assembly, new_project


JSON_FILTER = [
    ("AURA PLM / JSON", "*.json"),
    ("Все файлы", "*.*"),
]


def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def normalize_document(raw: Any) -> dict:
    """Принять полный документ или экспорт проекта/сборки/детали из HTML-менеджера."""
    data = _as_dict(raw)
    export_type = str(data.get("exportType") or "").strip().lower()

    if export_type == "project" and isinstance(data.get("data"), dict):
        doc = empty_document()
        doc["projects"] = [data["data"]]
        return _ensure_shape(doc)

    if export_type == "assembly" and isinstance(data.get("data"), dict):
        doc = empty_document()
        prj = new_project(data.get("projectName") or "Импортированная сборка")
        prj["assemblies"] = [data["data"]]
        doc["projects"] = [prj]
        return _ensure_shape(doc)

    if export_type == "part" and isinstance(data.get("data"), dict):
        doc = empty_document()
        prj = new_project("Импортированная деталь")
        asm = new_assembly("Сборка")
        asm["parts"] = [data["data"]]
        prj["assemblies"] = [asm]
        doc["projects"] = [prj]
        return _ensure_shape(doc)

    if isinstance(data.get("projects"), list):
        return _ensure_shape(data)

    # Иногда экспортируют список проектов напрямую
    if isinstance(raw, list):
        doc = empty_document()
        doc["projects"] = [p for p in raw if isinstance(p, dict)]
        return _ensure_shape(doc)

    raise ValueError("Файл не похож на документ AURA PLM или экспорт менеджера проектов.")


def _ensure_shape(doc: dict) -> dict:
    base = empty_document()
    base.update({k: v for k, v in doc.items() if k != "library"})
    lib = empty_library()
    incoming = _as_dict(doc.get("library"))
    for key in lib:
        if key in incoming and incoming[key] is not None:
            lib[key] = incoming[key]
    base["library"] = lib
    if not isinstance(base.get("projects"), list):
        base["projects"] = []
    if not isinstance(base.get("cart"), list):
        base["cart"] = []
    cad = _as_dict(base.get("cad"))
    if not isinstance(cad.get("links"), list):
        cad["links"] = []
    base["cad"] = cad
    vault = _as_dict(base.get("vault"))
    vault.setdefault("root", "")
    base["vault"] = vault
    base["owner"] = str(base.get("owner") or "")
    sel = _as_dict(base.get("selection"))
    base["selection"] = {
        "type": sel.get("type"),
        "projectId": sel.get("projectId"),
        "assemblyId": sel.get("assemblyId"),
        "partId": sel.get("partId"),
    }
    base["app"] = "AURA PLM System"
    base["version"] = int(base.get("version") or 1)
    return base


def load_document(path: str | Path, username: str | None = None, key: bytes | None = None) -> dict:
    text = Path(path).read_text(encoding="utf-8")
    from .auth import decrypt_document, is_encrypted, peek_owner

    if is_encrypted(text):
        owner = peek_owner(text)
        if username and owner and owner.casefold() != username.casefold():
            raise PermissionError(f"Файл принадлежит пользователю «{owner}».")
        if not username or not key:
            raise PermissionError("Чтобы открыть файл, войдите в аккаунт.")
        text = decrypt_document(text, username, key)
    raw = json.loads(text)
    doc = normalize_document(raw)
    owner = doc.get("owner")
    if owner and username and str(owner).casefold() != username.casefold():
        raise PermissionError(f"Файл принадлежит пользователю «{owner}».")
    if username:
        doc["owner"] = username
    return doc


def save_document(path: str | Path, doc: dict, username: str | None = None, key: bytes | None = None) -> None:
    payload = normalize_document(doc)
    if username:
        payload["owner"] = username
    raw = json.dumps(payload, ensure_ascii=False, indent=2)
    if username and key:
        from .auth import encrypt_document

        text = encrypt_document(raw, username, key)
    else:
        text = raw
    Path(path).write_text(text, encoding="utf-8")


def merge_document(target: dict, incoming: dict) -> None:
    """Добавить проекты и библиотеку из incoming в текущий документ."""
    src = normalize_document(incoming)
    target.setdefault("projects", []).extend(src.get("projects") or [])
    tlib = target.setdefault("library", empty_library())
    slib = src.get("library") or {}
    for key in ("workers", "materials", "productTypes", "standards", "coatings"):
        existing = tlib.setdefault(key, [])
        seen = {json.dumps(x, ensure_ascii=False, sort_keys=True) if not isinstance(x, str) else x.casefold() for x in existing}
        for item in slib.get(key) or []:
            token = item.casefold() if isinstance(item, str) else json.dumps(item, ensure_ascii=False, sort_keys=True)
            if token not in seen:
                existing.append(item)
                seen.add(token)
