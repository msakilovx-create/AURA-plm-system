"""Экспорт корзины и иерархии в Excel — те же столбцы, ширины в мм и границы, что в менеджере."""

from __future__ import annotations

import csv
from datetime import date
from io import BytesIO
from pathlib import Path

from .cart import build_hierarchy_rows

MM_CHAR = 1.9  # мм → ширина столбца Excel (как в менеджере)
MM_PT = 72 / 25.4


def _mm_width(mm: float | None, header: str) -> float:
    if mm is None:
        return max(8, len(header) + 2)
    return mm / MM_CHAR


def _mm_height(mm: float) -> float:
    return mm * MM_PT


def _sanitize(name: str) -> str:
    bad = '<>:"/\\|?*'
    s = "".join("_" if c in bad else c for c in (name or "file"))
    return s.strip(" ._")[:80] or "file"


def _thin_border():
    from openpyxl.styles import Border, Side

    s = Side(style="thin", color="FF000000")
    return Border(top=s, left=s, bottom=s, right=s)


def _header_fill():
    from openpyxl.styles import PatternFill

    return PatternFill("solid", fgColor="FFE8EEF7")


def _photo_path(raw: str) -> Path | None:
    if not raw:
        return None
    if str(raw).startswith("data:image"):
        return None
    p = Path(raw)
    return p if p.exists() and p.is_file() else None


def _embed_photo(ws, wb, path: Path, col_idx: int, row_idx: int):
    """col_idx 0-based, row_idx 0-based including header."""
    from openpyxl.drawing.image import Image as XLImage
    from PIL import Image as PILImage

    img_h_mm = 12
    img_h_px = img_h_mm / 25.4 * 96
    im = PILImage.open(path)
    w, h = im.size
    ratio = (w / h) if h else 1
    w_px = max(4, img_h_px * ratio)
    buf = BytesIO()
    ext = "png"
    if path.suffix.lower() in {".jpg", ".jpeg"}:
        ext = "jpeg"
        im.convert("RGB").save(buf, format="JPEG", quality=85)
    else:
        im.convert("RGBA").save(buf, format="PNG")
    buf.seek(0)
    xl = XLImage(buf)
    xl.width = w_px
    xl.height = img_h_px
    # oneCell: col G = 6 for cart, col F = 5 for hierarchy
    from openpyxl.utils import get_column_letter

    cell = f"{get_column_letter(col_idx + 1)}{row_idx + 1}"
    xl.anchor = cell
    ws.add_image(xl)


def export_cart_xlsx(doc: dict, dest: Path) -> Path:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, numbers

    items = doc.get("cart") or []
    headers = [
        "Наименование", "Обозначение", "Материал", "Кол-во", "Цена за ед.",
        "Сумма", "Изображение", "Примечание", "Путь к папке", "Имя файла",
    ]
    widths_mm = [40, 40, 30, 25, 25, 25, None, 40, 40, 40]
    wb = Workbook()
    wb.properties.creator = "AURA PLM System"
    ws = wb.active
    ws.title = "Корзина"
    ws.sheet_properties.defaultRowHeight = 18
    from openpyxl.utils import get_column_letter

    for i, (h, mm) in enumerate(zip(headers, widths_mm), start=1):
        ws.column_dimensions[get_column_letter(i)].width = _mm_width(mm, h)

    border = _thin_border()
    fill = _header_fill()
    header_font = Font(bold=True, name="Calibri", size=11)
    body_font = Font(name="Calibri", size=11)
    top = Alignment(vertical="top", wrap_text=True)
    center = Alignment(vertical="top", horizontal="center", wrap_text=True)

    ws.append(headers)
    ws.row_dimensions[1].height = _mm_height(8)
    for cell in ws[1]:
        cell.font = header_font
        cell.alignment = center
        cell.fill = fill
        cell.border = border

    total = 0.0
    for i, c in enumerate(items):
        unit = float(c.get("unitCost") or 0)
        qty = float(c.get("qty") or 1)
        s = unit * qty
        total += s
        photo = _photo_path(c.get("photo") or "")
        ws.append([
            c.get("name") or "",
            c.get("designation") or "",
            c.get("material") or "",
            qty,
            unit,
            s,
            "",
            c.get("note") or "",
            c.get("folderPath") or "",
            Path(c.get("filePath") or "").name or (c.get("filePath") or ""),
        ])
        r = i + 2
        ws.row_dimensions[r].height = _mm_height(13 if photo else 6)
        for col, cell in enumerate(ws[r], start=1):
            cell.font = body_font
            cell.alignment = top
            cell.border = border
            if col in (4, 5, 6):
                cell.number_format = "#,##0.00"
        if photo:
            try:
                _embed_photo(ws, wb, photo, 6, r - 1)
            except Exception:
                ws.cell(r, 7).value = "[есть]"

    ws.append(["", "", "", "", "ИТОГО", total, "", "", "", ""])
    last = ws.max_row
    ws.row_dimensions[last].height = _mm_height(6)
    for cell in ws[last]:
        cell.font = Font(bold=True, name="Calibri", size=11)
        cell.alignment = top
        cell.border = border
        if cell.column in (5, 6):
            cell.number_format = "#,##0.00"
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    wb.save(dest)
    return dest


def export_hierarchy_xlsx(prj: dict, dest: Path) -> Path:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font
    from openpyxl.utils import get_column_letter

    rows = build_hierarchy_rows(prj)
    headers = ["Уровень", "Наименование", "Обозначение", "Тип", "Принадлежность (сборка)", "Изображение"]
    widths_mm = [12, 40, 40, 30, 40, None]
    wb = Workbook()
    wb.properties.creator = "AURA PLM System"
    ws = wb.active
    ws.title = "Иерархия"
    for i, (h, mm) in enumerate(zip(headers, widths_mm), start=1):
        ws.column_dimensions[get_column_letter(i)].width = _mm_width(mm, h)
    border = _thin_border()
    fill = _header_fill()
    header_font = Font(bold=True, name="Calibri", size=11)
    body_font = Font(name="Calibri", size=11)
    top = Alignment(vertical="top", wrap_text=True)
    center = Alignment(vertical="top", horizontal="center", wrap_text=True)
    ws.append(headers)
    ws.row_dimensions[1].height = _mm_height(8)
    for cell in ws[1]:
        cell.font = header_font
        cell.alignment = center
        cell.fill = fill
        cell.border = border
    for i, r in enumerate(rows):
        photo = _photo_path(r.get("photo") or "")
        ws.append([r.get("level"), r.get("name") or "", r.get("designation") or "", r.get("type") or "", r.get("parent") or "", ""])
        rr = i + 2
        ws.row_dimensions[rr].height = _mm_height(13 if photo else 6)
        for cell in ws[rr]:
            cell.font = body_font
            cell.alignment = top
            cell.border = border
        if photo:
            try:
                _embed_photo(ws, wb, photo, 5, rr - 1)
            except Exception:
                ws.cell(rr, 6).value = "[есть]"
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    wb.save(dest)
    return dest


def export_cart_csv(doc: dict, dest: Path) -> Path:
    dest = Path(dest)
    items = doc.get("cart") or []
    headers = [
        "Наименование", "Обозначение", "Материал", "Кол-во", "Цена за ед.",
        "Сумма", "Изображение", "Примечание", "Путь к папке", "Имя файла",
    ]
    total = 0.0
    with dest.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(headers)
        for c in items:
            unit = float(c.get("unitCost") or 0)
            qty = float(c.get("qty") or 1)
            s = unit * qty
            total += s
            w.writerow([
                c.get("name") or "",
                c.get("designation") or "",
                c.get("material") or "",
                str(int(qty) if qty == int(qty) else qty).replace(".", ","),
                f"{unit:.2f}".replace(".", ","),
                f"{s:.2f}".replace(".", ","),
                "[есть]" if c.get("photo") else "",
                c.get("note") or "",
                c.get("folderPath") or "",
                c.get("filePath") or "",
            ])
        w.writerow(["", "", "", "", "ИТОГО", f"{total:.2f}".replace(".", ","), "", "", "", ""])
    return dest


def export_hierarchy_csv(prj: dict, dest: Path) -> Path:
    dest = Path(dest)
    rows = build_hierarchy_rows(prj)
    with dest.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["Уровень", "Наименование", "Обозначение", "Тип", "Принадлежность (сборка)", "Изображение"])
        for r in rows:
            w.writerow([
                r.get("level"),
                r.get("name") or "",
                r.get("designation") or "",
                r.get("type") or "",
                r.get("parent") or "",
                "[есть]" if r.get("photo") else "",
            ])
    return dest


def default_cart_xlsx_name() -> str:
    return f"korzina_pokupnina_{date.today().isoformat()}.xlsx"


def default_hierarchy_xlsx_name(prj: dict) -> str:
    return f"иерархия_{_sanitize(prj.get('name') or 'project')}.xlsx"
