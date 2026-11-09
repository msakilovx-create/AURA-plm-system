"""Диалоги связи с CAD и выгрузки проекта в AURA PLM."""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from datetime import datetime
from pathlib import Path

from . import __app_name__
from .cad.detect import detect_cad_systems
from .cad.importing import (
    attach_cad_file,
    import_cad_source,
    import_from_running_cad,
    new_cad_link,
    open_in_cad,
    reveal_in_explorer,
    resync_link,
)
from .cad.live import GrabError, file_filter_for
from .cad.systems import file_dialog_filter
from .cad.teamcenter import TC_FILE_FILTER, find_recent_teamcenter_exports, import_teamcenter
from .model import ensure_cad_files
from .theme import DIM, OK, PM_HDR, WORK, panel_header


def open_cad_hub(app) -> None:
    if getattr(app, "_cad_win", None) and app._cad_win.winfo_exists():
        app._cad_win.lift()
        return
    win = tk.Toplevel(app.root)
    win.title("Связь с CAD")
    win.configure(bg=WORK)
    win.geometry("780x560")
    win.transient(app.root)
    app._cad_win = win
    panel_header(win, "Связь с CAD-системами", PM_HDR, "выгрузка состава в AURA PLM")

    body = ttk.Frame(win, style="PM.TFrame")
    body.pack(fill="both", expand=True, padx=8, pady=8)

    ttk.Label(body, text="Обнаруженные системы", style="Dim.TLabel").pack(anchor="w")
    cols = ("name", "status", "run")
    table = ttk.Treeview(body, columns=cols, show="headings", height=8, selectmode="browse")
    table.heading("name", text="CAD")
    table.heading("status", text="На компьютере")
    table.heading("run", text="Сейчас")
    table.column("name", width=240)
    table.column("status", width=160)
    table.column("run", width=140)
    table.pack(fill="x", pady=(4, 8))

    def reload_systems():
        table.delete(*table.get_children())
        app._cad_detected = detect_cad_systems()
        for sys in app._cad_detected:
            st = "установлена" if sys["installed"] else "не найдена"
            run = "запущена" if sys["running"] else "—"
            table.insert("", "end", iid=sys["id"], values=(sys["name"], st, run), tags=("on",) if sys["installed"] else ("off",))
        table.tag_configure("on", foreground=OK)
        table.tag_configure("off", foreground=DIM)

    reload_systems()

    btns = ttk.Frame(body, style="PM.TFrame")
    btns.pack(fill="x", pady=(0, 10))

    def selected_system():
        sel = table.selection()
        return sel[0] if sel else None

    def do_import_file():
        path = filedialog.askopenfilename(
            title="Выгрузить сборку или деталь из CAD",
            filetypes=file_dialog_filter(),
            parent=win,
        )
        if path:
            _run_import(app, path, selected_system(), win)

    def do_import_folder():
        path = filedialog.askdirectory(title="Папка проекта CAD", parent=win)
        if path:
            _run_import(app, path, selected_system(), win)

    def do_grab_live():
        sid = selected_system()
        if not sid:
            messagebox.showinfo(__app_name__, "Выберите CAD в списке.", parent=win)
            return
        if sid == "teamcenter":
            import_teamcenter_into(app, win)
            return
        try:
            prj = import_from_running_cad(sid)
        except GrabError as exc:
            if exc.managed:
                choice = messagebox.askyesnocancel(
                    __app_name__,
                    str(exc) + "\n\nДа — выгрузить PLMXML из Teamcenter\nНет — указать файл NX / сборки на диске",
                    parent=win,
                )
                if choice is None:
                    return
                if choice:
                    import_teamcenter_into(app, win)
                    return
            path = filedialog.askopenfilename(
                title="Укажите сохранённую сборку на диске",
                filetypes=file_filter_for(sid),
                parent=win,
            )
            if not path:
                return
            _run_import(app, path, sid, win)
            return
        except Exception as exc:
            messagebox.showerror(__app_name__, str(exc), parent=win)
            return
        _accept_project(app, prj, sid, prj.get("cadSource") or "", win)

    ttk.Button(btns, text="Выгрузить файл сборки…", command=do_import_file).pack(side="left", padx=(0, 6))
    ttk.Button(btns, text="Выгрузить папку проекта…", command=do_import_folder).pack(side="left", padx=6)
    ttk.Button(btns, text="Забрать из запущенной CAD", command=do_grab_live, style="Accent.TButton").pack(side="left", padx=6)
    ttk.Button(btns, text="Teamcenter…", command=lambda: import_teamcenter_into(app, win)).pack(side="left", padx=6)
    ttk.Button(btns, text="Обновить список", command=reload_systems).pack(side="right")

    ttk.Label(
        body,
        text="Файл или папка разбирается в дерево проект → сборка → деталь. "
        "Для SolidWorks, КОМПАС и STEP читаются ссылки на компоненты. "
        "Teamcenter: выгрузите PLMXML / briefcase / CSV BOM из Structure Manager и укажите файл.",
        style="Dim.TLabel",
        wraplength=740,
        justify="left",
    ).pack(anchor="w", pady=(0, 10))

    ttk.Label(body, text="Связанные источники этого документа", style="Dim.TLabel").pack(anchor="w")
    links = ttk.Treeview(body, columns=("sys", "src", "when"), show="headings", height=6)
    links.heading("sys", text="Система")
    links.heading("src", text="Путь")
    links.heading("when", text="Синхронизация")
    links.column("sys", width=140)
    links.column("src", width=420)
    links.column("when", width=150)
    links.pack(fill="both", expand=True, pady=(4, 8))

    def reload_links():
        links.delete(*links.get_children())
        for link in (app.doc.get("cad") or {}).get("links") or []:
            links.insert("", "end", iid=link["id"], values=(
                link.get("system") or "",
                link.get("sourcePath") or "",
                link.get("lastSync") or "",
            ))

    def do_resync():
        sel = links.selection()
        if not sel:
            messagebox.showinfo(__app_name__, "Выберите связь для синхронизации.", parent=win)
            return
        link = next((x for x in (app.doc.get("cad") or {}).get("links") or [] if x["id"] == sel[0]), None)
        if not link:
            return
        from .model import find_project

        prj = find_project(app.doc, link.get("projectId")) if link.get("projectId") else None
        if prj is None:
            messagebox.showerror(__app_name__, "Связанный проект не найден.", parent=win)
            return
        try:
            fresh = resync_link(prj)
        except Exception as exc:
            messagebox.showerror(__app_name__, str(exc), parent=win)
            return
        prj["assemblies"] = fresh.get("assemblies") or []
        prj["cadSource"] = fresh.get("cadSource") or prj.get("cadSource")
        prj["folderPath"] = fresh.get("folderPath") or prj.get("folderPath")
        link["lastSync"] = datetime.now().strftime("%d.%m.%Y %H:%M")
        app.mark_dirty()
        app.refresh_all()
        reload_links()
        messagebox.showinfo(__app_name__, f"Состав обновлён: {prj.get('name')}", parent=win)

    def do_open_source():
        sel = links.selection()
        if not sel:
            return
        link = next((x for x in (app.doc.get("cad") or {}).get("links") or [] if x["id"] == sel[0]), None)
        if not link:
            return
        try:
            reveal_in_explorer(link.get("sourcePath") or "")
        except Exception as exc:
            messagebox.showerror(__app_name__, str(exc), parent=win)

    lbtns = ttk.Frame(body, style="PM.TFrame")
    lbtns.pack(fill="x")
    ttk.Button(lbtns, text="Синхронизировать состав", command=do_resync).pack(side="left", padx=(0, 6))
    ttk.Button(lbtns, text="Показать папку", command=do_open_source).pack(side="left")
    reload_links()
    app._cad_reload_links = reload_links


def import_teamcenter_into(app, parent=None) -> None:
    recent = find_recent_teamcenter_exports()
    path = filedialog.askopenfilename(
        title="Выгрузить состав из Teamcenter (PLMXML, briefcase, CSV)",
        filetypes=TC_FILE_FILTER,
        initialdir=str(recent[0].parent) if recent else None,
        parent=parent or app.root,
    )
    if not path:
        return
    try:
        prj = import_teamcenter(path)
    except Exception as exc:
        messagebox.showerror(__app_name__, f"Не удалось выгрузить Teamcenter:\n{exc}", parent=parent)
        return
    _accept_project(app, prj, "teamcenter", path, parent or app.root)


def _run_import(app, path: str, system_id: str | None, parent) -> None:
    try:
        prj = import_cad_source(path, system_id)
    except Exception as exc:
        messagebox.showerror(__app_name__, f"Не удалось выгрузить CAD-проект:\n{exc}", parent=parent)
        return
    _accept_project(app, prj, system_id or "", path, parent)


def _accept_project(app, prj: dict, system_id: str, source: str, parent) -> None:
    app.doc.setdefault("projects", []).append(prj)
    app.doc.setdefault("cad", {}).setdefault("links", []).append(
        new_cad_link(system_id or "step", source or prj.get("cadSource") or "", prj["id"])
    )
    if app.doc["cad"]["links"]:
        app.doc["cad"]["links"][-1]["lastSync"] = datetime.now().strftime("%d.%m.%Y %H:%M")
    copied = 0
    try:
        from .vault import ingest_project, vault_root

        copied = ingest_project(app.doc, prj, source)
    except Exception:
        copied = 0
    app.mark_dirty()
    app.refresh_all()
    if app.tree.exists(prj["id"]):
        app.tree.selection_set(prj["id"])
        app.on_tree_select()
    n_asm = len(prj.get("assemblies") or [])
    n_parts = _count_parts(prj)
    extra = f"\nВ хранилище скопировано файлов: {copied}" if copied else ""
    try:
        from .vault import vault_root

        extra += f"\n{vault_root(app.doc)}"
    except Exception:
        pass
    messagebox.showinfo(
        __app_name__,
        f"Выгружено в AURA PLM:\n{prj.get('name')}\nсборок: {n_asm}, деталей: {n_parts}{extra}",
        parent=parent,
    )
    if getattr(app, "_cad_reload_links", None):
        try:
            app._cad_reload_links()
        except tk.TclError:
            pass


def _count_parts(prj: dict) -> int:
    total = 0

    def walk(asm):
        nonlocal total
        total += len(asm.get("parts") or [])
        for a in asm.get("assemblies") or []:
            walk(a)

    for a in prj.get("assemblies") or []:
        walk(a)
    return total


def pick_cad_file_for_node(app, node: dict, slot: str) -> None:
    path = filedialog.askopenfilename(
        title="Привязать CAD-файл",
        filetypes=file_dialog_filter(),
        parent=app.root,
    )
    if not path:
        return
    prj = app.current_project()
    if prj:
        from .vault import ingest_file

        kind, _node = app.current_node()
        ingest_file(app.doc, prj, node, kind or "part", path)
    else:
        attach_cad_file(node, Path(path))
        if slot and slot in ensure_cad_files(node):
            node["cadFiles"][slot]["filePath"] = str(Path(path).resolve())
            node["cadFiles"][slot]["folderPath"] = str(Path(path).resolve().parent)
    app.mark_dirty()
    app.show_selection()


def open_node_cad(app, node: dict) -> None:
    ensure_cad_files(node)
    path = (
        node.get("filePath")
        or (node.get("cadFiles") or {}).get("sw", {}).get("filePath")
        or (node.get("cadFiles") or {}).get("native", {}).get("filePath")
        or (node.get("cadFiles") or {}).get("stp", {}).get("filePath")
    )
    if not path:
        messagebox.showinfo(__app_name__, "К этому узлу ещё не привязан CAD-файл.")
        return
    try:
        open_in_cad(path)
    except Exception as exc:
        messagebox.showerror(__app_name__, str(exc))


def build_cad_card(app, parent, node: dict) -> None:
    card = app._card(parent, "Файлы CAD")
    ensure_cad_files(node)
    slots = [
        ("sw", "SolidWorks"),
        ("stp", "STEP"),
        ("native", "Нативный CAD"),
        ("pdf", "PDF / чертёж"),
    ]
    for key, title in slots:
        slot = node["cadFiles"][key]
        row = ttk.Frame(card, style="Card.TFrame")
        row.pack(fill="x", pady=3)
        ttk.Label(row, text=title, style="CardDim.TLabel", width=16).pack(side="left")
        var = tk.StringVar(value=slot.get("filePath") or "")

        def save(k=key, v=var):
            if app._building:
                return
            ensure_cad_files(node)[k]["filePath"] = v.get()
            if v.get():
                node["filePath"] = v.get()
                node["folderPath"] = str(Path(v.get()).parent) if v.get() else node.get("folderPath") or ""
            app.mark_dirty()

        var.trace_add("write", lambda *_a, k=key, v=var: save(k, v))
        ttk.Entry(row, textvariable=var).pack(side="left", fill="x", expand=True, padx=6)

        def browse(k=key):
            pick_cad_file_for_node(app, node, k)

        def open_slot(k=key):
            p = node["cadFiles"][k].get("filePath")
            if not p:
                return
            try:
                open_in_cad(p)
            except Exception as exc:
                messagebox.showerror(__app_name__, str(exc))

        def show_slot(k=key):
            p = node["cadFiles"][k].get("filePath")
            if not p:
                return
            try:
                reveal_in_explorer(p)
            except Exception as exc:
                messagebox.showerror(__app_name__, str(exc))

        ttk.Button(row, text="…", width=3, command=browse).pack(side="left", padx=2)
        ttk.Button(row, text="Открыть", command=open_slot).pack(side="left", padx=2)
        ttk.Button(row, text="Папка", command=show_slot).pack(side="left", padx=2)

    extra = ttk.Frame(card, style="Card.TFrame")
    extra.pack(fill="x", pady=(8, 0))
    ttk.Button(extra, text="Папка хранилища", command=app.open_node_vault).pack(side="left", padx=(0, 6))
    ttk.Button(extra, text="Открыть в CAD", command=app.cad_open_selected).pack(side="left", padx=4)
    ttk.Button(extra, text="Выбрать CAD…", command=app.cad_open_with).pack(side="left", padx=4)
    hint = ttk.Label(
        card,
        text="Файлы копируются в хранилище AURA (Documents\\AURA_Vault). «Открыть в CAD» запускает систему с файла из хранилища.",
        style="CardDim.TLabel",
        wraplength=640,
    )
    hint.pack(anchor="w", pady=(6, 0))
