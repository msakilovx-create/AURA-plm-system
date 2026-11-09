"""Окно корзины покупнины."""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path

from . import __app_name__
from .cart import (
    cart_count,
    cart_grand_total,
    cart_line_total,
    clear_cart,
    remove_from_cart,
    update_cart_note,
    update_cart_qty,
)
from .excel_export import default_cart_xlsx_name, export_cart_csv, export_cart_xlsx
from .model import format_money
from .theme import DANGER, NAVY, PM_BG, PM_HDR, TEXT, WORK, panel_header


def open_cart_window(app) -> None:
    if getattr(app, "_cart_win", None) and app._cart_win.winfo_exists():
        app._cart_win.lift()
        _fill(app)
        return
    win = tk.Toplevel(app.root)
    win.title("Корзина покупнины")
    win.geometry("860x560")
    win.configure(bg=WORK)
    win.transient(app.root)
    app._cart_win = win
    panel_header(win, "Корзина покупнины", PM_HDR, "закупаемый комплект")
    top = ttk.Frame(win, style="PM.TFrame")
    top.pack(fill="x", padx=10, pady=8)
    app._cart_summary = ttk.Label(top, text="", style="Dim.TLabel")
    app._cart_summary.pack(side="left")
    btns = ttk.Frame(top, style="PM.TFrame")
    btns.pack(side="right")
    ttk.Button(btns, text="Excel", command=lambda: _export_xlsx(app)).pack(side="left", padx=3)
    ttk.Button(btns, text="CSV", command=lambda: _export_csv(app)).pack(side="left", padx=3)
    ttk.Button(btns, text="Очистить", command=lambda: _clear(app)).pack(side="left", padx=3)

    cols = ("kind", "name", "code", "mat", "qty", "unit", "sum", "note")
    wrap = ttk.Frame(win, style="PM.TFrame")
    wrap.pack(fill="both", expand=True, padx=10, pady=(0, 8))
    tree = ttk.Treeview(wrap, columns=cols, show="headings", selectmode="browse")
    heads = {
        "kind": "Вид", "name": "Наименование", "code": "Обозначение", "mat": "Материал",
        "qty": "Кол-во", "unit": "Цена, ₽", "sum": "Сумма, ₽", "note": "Примечание",
    }
    widths = {"kind": 70, "name": 180, "code": 120, "mat": 110, "qty": 70, "unit": 90, "sum": 100, "note": 160}
    for c in cols:
        tree.heading(c, text=heads[c])
        tree.column(c, width=widths[c], stretch=c in ("name", "note"))
    y = ttk.Scrollbar(wrap, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=y.set)
    tree.pack(side="left", fill="both", expand=True)
    y.pack(side="right", fill="y")
    app._cart_tree = tree
    row = ttk.Frame(win, style="PM.TFrame")
    row.pack(fill="x", padx=10, pady=(0, 10))
    ttk.Button(row, text="Кол-во…", command=lambda: _edit_qty(app)).pack(side="left", padx=3)
    ttk.Button(row, text="Примечание…", command=lambda: _edit_note(app)).pack(side="left", padx=3)
    ttk.Button(row, text="Убрать", command=lambda: _remove(app)).pack(side="left", padx=3)
    tree.bind("<Double-1>", lambda _e: _edit_qty(app))
    _fill(app)


def _fill(app):
    tree = getattr(app, "_cart_tree", None)
    if not tree or not tree.winfo_exists():
        return
    tree.delete(*tree.get_children())
    for c in app.doc.get("cart") or []:
        tree.insert("", "end", iid=c["id"], values=(
            "Деталь" if c.get("kind") == "part" else "Сборка",
            c.get("name") or "",
            c.get("designation") or "",
            c.get("material") or "",
            c.get("qty") or 1,
            format_money(c.get("unitCost")),
            format_money(cart_line_total(c)),
            c.get("note") or "",
        ))
    n = len(app.doc.get("cart") or [])
    qty = cart_count(app.doc)
    total = cart_grand_total(app.doc)
    if getattr(app, "_cart_summary", None):
        app._cart_summary.configure(
            text=f"Позиций: {n}  ·  единиц: {qty}  ·  Итого: {format_money(total)} ₽"
        )
    if getattr(app, "_cart_badge", None):
        app._cart_badge.configure(text=str(qty if n else "0"))


def _sel(app):
    tree = app._cart_tree
    s = tree.selection()
    return s[0] if s else None


def _edit_qty(app):
    cid = _sel(app)
    if not cid:
        return
    from tkinter import simpledialog

    item = next((c for c in app.doc.get("cart") or [] if c["id"] == cid), None)
    if not item:
        return
    val = simpledialog.askinteger("Кол-во", "Количество:", initialvalue=int(item.get("qty") or 1), minvalue=1, parent=app._cart_win)
    if val is None:
        return
    update_cart_qty(app.doc, cid, val)
    app.mark_dirty()
    _fill(app)
    app.update_cart_badge()


def _edit_note(app):
    cid = _sel(app)
    if not cid:
        return
    from tkinter import simpledialog

    item = next((c for c in app.doc.get("cart") or [] if c["id"] == cid), None)
    if not item:
        return
    val = simpledialog.askstring("Примечание", "Примечание к заказу:", initialvalue=item.get("note") or "", parent=app._cart_win)
    if val is None:
        return
    update_cart_note(app.doc, cid, val)
    app.mark_dirty()
    _fill(app)


def _remove(app):
    cid = _sel(app)
    if not cid:
        return
    remove_from_cart(app.doc, cid)
    app.mark_dirty()
    _fill(app)
    app.update_cart_badge()


def _clear(app):
    if not (app.doc.get("cart") or []):
        return
    if not messagebox.askyesno(__app_name__, "Очистить всю корзину покупнины?", parent=app._cart_win):
        return
    clear_cart(app.doc)
    app.mark_dirty()
    _fill(app)
    app.update_cart_badge()


def _export_xlsx(app):
    if not (app.doc.get("cart") or []):
        messagebox.showinfo(__app_name__, "Корзина пуста.", parent=app._cart_win)
        return
    path = filedialog.asksaveasfilename(
        title="Экспорт корзины в Excel",
        defaultextension=".xlsx",
        initialfile=default_cart_xlsx_name(),
        filetypes=[("Excel", "*.xlsx"), ("Все файлы", "*.*")],
        parent=app._cart_win,
    )
    if not path:
        return
    try:
        export_cart_xlsx(app.doc, Path(path))
    except ImportError:
        csv_path = Path(path).with_suffix(".csv")
        export_cart_csv(app.doc, csv_path)
        messagebox.showinfo(__app_name__, f"openpyxl не установлен, сохранён CSV:\n{csv_path}", parent=app._cart_win)
        return
    except Exception as exc:
        messagebox.showerror(__app_name__, str(exc), parent=app._cart_win)
        return
    messagebox.showinfo(__app_name__, f"Сохранено:\n{path}", parent=app._cart_win)


def _export_csv(app):
    if not (app.doc.get("cart") or []):
        return
    path = filedialog.asksaveasfilename(
        title="Экспорт корзины в CSV",
        defaultextension=".csv",
        initialfile=default_cart_xlsx_name().replace(".xlsx", ".csv"),
        filetypes=[("CSV", "*.csv")],
        parent=app._cart_win,
    )
    if not path:
        return
    export_cart_csv(app.doc, Path(path))
    messagebox.showinfo(__app_name__, f"Сохранено:\n{path}", parent=app._cart_win)
