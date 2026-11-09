"""Оконное приложение AURA PLM System."""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from pathlib import Path

from . import __app_name__, __version__
from .model import (
    STATUS_LABELS,
    STATUS_MARKS,
    assembly_matches,
    checklist_stats,
    delete_node,
    duplicate_node,
    empty_document,
    find_assembly,
    find_part_in_assembly,
    find_project,
    format_money,
    materials_from_library,
    new_assembly,
    new_category,
    new_item,
    new_part,
    new_project,
    new_worker,
    next_status,
    node_labor_cost,
    node_material_cost,
    node_matches,
    node_unit_cost,
    product_types,
    project_labor_cost,
    project_matches,
    project_material_cost,
    project_total_cost,
    seed_document,
    tree_label,
    walk_checklists,
    workers_pay_sum,
)
from .cad.detect import detect_cad_systems
from .cad.importing import attach_cad_file, import_from_running_cad
from .cad.systems import file_dialog_filter
from .cad_ui import build_cad_card, open_cad_hub, open_node_cad
from .media import load_preview, node_model_path, node_photo_path, placeholder_icon
from .view3d import cached_mesh_path, draw_mesh_preview, load_model, load_stl, open_model
from .storage import JSON_FILTER, load_document, merge_document, save_document
from .theme import (
    CMD_BG,
    DANGER,
    DIM,
    FM_BG,
    FM_HDR,
    FM_SEL,
    FM_SEL_FG,
    NAVY,
    NAVY_DEEP,
    OK,
    PM_BG,
    PM_BORDER,
    PM_GROUP,
    PM_GROUP_HDR,
    PM_HDR,
    STATUS_BG,
    SW_BLUE,
    SW_ORANGE,
    SW_RED,
    TEXT,
    WORK,
    apply_style,
    command_group,
    panel_header,
    v_sep,
)

KIND_ICONS = {"project": "📁", "assembly": "🧩", "part": "🔧"}
KIND_TITLES = {"project": "Проект", "assembly": "Сборка", "part": "Деталь"}


def _parse_custom_checklist(raw: str) -> list:
    cats = []
    current = None

    def ensure_cat(title: str):
        nonlocal current
        current = new_category(title.strip() or "Чек-лист", [])
        cats.append(current)
        return current

    for line in (raw or "").splitlines():
        text = line.strip()
        if not text:
            continue
        if text.startswith("#"):
            ensure_cat(text.lstrip("#").strip() or "Чек-лист")
            continue
        if text.endswith(":") and not text.startswith(("-", "•", "*")):
            ensure_cat(text[:-1].strip() or "Чек-лист")
            continue
        if text[0] in "-•*" and len(text) > 1 and text[1] in " \t":
            text = text[1:].strip()
        if not current:
            ensure_cat("Чек-лист")
        if text:
            current["items"].append(new_item(text))
    return [c for c in cats if c.get("items")]


class Scrollable(ttk.Frame):
    def __init__(self, parent, **kw):
        super().__init__(parent, **kw)
        self.canvas = tk.Canvas(self, highlightthickness=0, bg=PM_BG, bd=0)
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.body = ttk.Frame(self.canvas, style="PM.TFrame")
        self._win = self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.canvas.configure(yscrollcommand=self.vsb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.vsb.pack(side="right", fill="y")
        self.body.bind("<Configure>", self._on_body)
        self.canvas.bind("<Configure>", self._on_canvas)
        self.canvas.bind("<Enter>", lambda _e: self._bind_wheel(True))
        self.canvas.bind("<Leave>", lambda _e: self._bind_wheel(False))

    def _on_body(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas(self, event):
        self.canvas.itemconfigure(self._win, width=event.width)

    def _bind_wheel(self, on: bool):
        if on:
            self.canvas.bind_all("<MouseWheel>", self._on_wheel)
        else:
            self.canvas.unbind_all("<MouseWheel>")

    def _on_wheel(self, event):
        self.canvas.yview_scroll(int(-event.delta / 120), "units")

    def clear(self):
        for child in self.body.winfo_children():
            child.destroy()
        self.canvas.yview_moveto(0)


class AuraApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(__app_name__)
        self.root.geometry("1280x800")
        self.root.minsize(960, 600)
        self.root.configure(bg=WORK)

        self.doc = empty_document()
        self.path: Path | None = None
        self.dirty = False
        self.search_query = ""
        self._building = False
        self._index: dict[str, tuple] = {}
        self._lib_win: tk.Toplevel | None = None
        self._cad_win: tk.Toplevel | None = None
        self._cart_win: tk.Toplevel | None = None
        self._preview_job = None
        self._preview_images = []
        self.user: dict | None = None
        self._file_key: bytes | None = None

        self._setup_style()
        self._ui_ready = False
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def run(self):
        from .login import mount_login

        mount_login(self.root, self._after_login)
        self.root.mainloop()

    def _after_login(self, session: dict):
        for w in self.root.winfo_children():
            w.destroy()
        self.root.geometry("1280x800")
        self.root.minsize(960, 600)
        self._apply_session(session)
        self._build_menu()
        self._build_ui()
        self._bind_keys()
        self._ui_ready = True
        self.refresh_all()
        self._set_dirty(False)
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def _apply_session(self, session: dict):
        from .vault import init_vault, set_vault_root

        from .auth import user_vault_root

        self.user = session["user"]
        self._file_key = session["key"]
        name = self.user.get("username") or ""
        self.doc = empty_document()
        self.doc["owner"] = name
        set_vault_root(self.doc, user_vault_root(name))
        init_vault(Path(self.doc["vault"]["root"]))
        self.path = None

    # ------------------------------------------------------------------ UI
    def _setup_style(self):
        apply_style(self.root)

    def _build_menu(self):
        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Новый документ", command=self.file_new, accelerator="Ctrl+N")
        file_menu.add_command(label="Создать пример…", command=self.file_seed)
        file_menu.add_separator()
        file_menu.add_command(label="Открыть…", command=self.file_open, accelerator="Ctrl+O")
        file_menu.add_command(label="Импортировать в текущий…", command=self.file_import)
        file_menu.add_separator()
        file_menu.add_command(label="Сохранить", command=self.file_save, accelerator="Ctrl+S")
        file_menu.add_command(label="Сохранить как…", command=self.file_save_as, accelerator="Ctrl+Shift+S")
        file_menu.add_separator()
        file_menu.add_command(label="Экспорт иерархии в Excel…", command=self.export_hierarchy_excel)
        file_menu.add_command(label="Экспорт корзины в Excel…", command=self.export_cart_excel)
        file_menu.add_separator()
        file_menu.add_command(label="Хранилище файлов…", command=self.choose_vault)
        file_menu.add_command(label="Открыть хранилище", command=self.open_vault_folder)
        file_menu.add_separator()
        file_menu.add_command(label="Выход", command=self.on_close)
        menubar.add_cascade(label="Файл", menu=file_menu)

        edit_menu = tk.Menu(menubar, tearoff=0)
        edit_menu.add_command(label="Новый проект", command=self.add_project)
        edit_menu.add_command(label="Добавить сборку", command=self.add_assembly)
        edit_menu.add_command(label="Добавить деталь", command=self.add_part)
        edit_menu.add_separator()
        edit_menu.add_command(label="Дублировать", command=self.duplicate_selected)
        edit_menu.add_command(label="Удалить", command=self.delete_selected)
        menubar.add_cascade(label="Правка", menu=edit_menu)

        view_menu = tk.Menu(menubar, tearoff=0)
        view_menu.add_command(label="Развернуть всё", command=lambda: self.expand_all(True))
        view_menu.add_command(label="Свернуть всё", command=lambda: self.expand_all(False))
        view_menu.add_separator()
        view_menu.add_command(label="Библиотека…", command=self.open_library)
        menubar.add_cascade(label="Вид", menu=view_menu)

        cad_menu = tk.Menu(menubar, tearoff=0)
        cad_menu.add_command(label="Связь с CAD…", command=self.open_cad_hub)
        cad_menu.add_separator()
        cad_menu.add_command(label="Выгрузить файл сборки…", command=self.cad_import_file)
        cad_menu.add_command(label="Выгрузить папку проекта…", command=self.cad_import_folder)
        cad_menu.add_command(label="Забрать из запущенной CAD", command=self.cad_grab_running)
        cad_menu.add_command(label="Выгрузить из Teamcenter…", command=self.cad_import_teamcenter)
        cad_menu.add_separator()
        cad_menu.add_command(label="Открыть узел в CAD", command=self.cad_open_selected)
        cad_menu.add_command(label="Открыть в выбранной CAD…", command=self.cad_open_with)
        cad_menu.add_command(label="Папка узла в хранилище", command=self.open_node_vault)
        menubar.add_cascade(label="CAD", menu=cad_menu)

        acc_menu = tk.Menu(menubar, tearoff=0)
        acc_menu.add_command(label="Сменить пароль…", command=self.change_password)
        acc_menu.add_command(label="Запросы на удаление…", command=self.open_delete_requests)
        acc_menu.add_separator()
        acc_menu.add_command(label="Выйти из аккаунта", command=self.logout)
        menubar.add_cascade(label="Аккаунт", menu=acc_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="О программе", command=self.show_about)
        menubar.add_cascade(label="Справка", menu=help_menu)
        self.root.config(menu=menubar)

    def _build_ui(self):
        title = tk.Frame(self.root, bg=NAVY)
        title.pack(fill="x")
        logo = tk.Canvas(title, width=26, height=26, bg=NAVY, highlightthickness=0)
        logo.pack(side="left", padx=(12, 8), pady=8)
        logo.create_rectangle(1, 1, 25, 25, fill=SW_RED, outline=NAVY_DEEP)
        logo.create_text(13, 13, text="A", fill="#FFFFFF", font=("Segoe UI", 12, "bold"))
        names = tk.Frame(title, bg=NAVY)
        names.pack(side="left", pady=6)
        tk.Label(names, text="AURA PLM System", bg=NAVY, fg="#FFFFFF", font=("Segoe UI", 13, "bold")).pack(anchor="w")
        tk.Label(
            names,
            text="Состав изделия  ·  проект → сборка → деталь",
            bg=NAVY,
            fg="#A9C4DA",
            font=("Segoe UI", 8),
        ).pack(anchor="w")

        cart_box = tk.Frame(title, bg=NAVY)
        cart_box.pack(side="right", padx=(0, 8), pady=6)
        self._cart_header_btn = tk.Button(
            cart_box, text="🛒 Корзина", command=self.open_cart,
            bg="#B91C1C", fg="#fff", relief="flat", font=("Segoe UI", 9, "bold"),
            cursor="hand2", activebackground="#991B1B", activeforeground="#fff",
        )
        self._cart_header_btn.pack(side="left")
        self._cart_badge = tk.Label(cart_box, text="0", bg="#FBBF24", fg="#111", font=("Segoe UI", 8, "bold"), padx=6)
        self._cart_badge.pack(side="left", padx=(4, 8), pady=4)

        cost_box = tk.Frame(title, bg=NAVY)
        cost_box.pack(side="right", padx=16, pady=6)
        tk.Label(cost_box, text="ИТОГО ПРОЕКТ", bg=NAVY, fg="#F0C27A", font=("Segoe UI", 7, "bold")).pack(anchor="e")
        self.header_cost = tk.Label(cost_box, text="—", bg=NAVY, fg="#FFFFFF", font=("Segoe UI", 14, "bold"))
        self.header_cost.pack(anchor="e")
        tk.Frame(self.root, bg=SW_ORANGE, height=3).pack(fill="x")

        cmd = tk.Frame(self.root, bg=CMD_BG)
        cmd.pack(fill="x")
        inner = tk.Frame(cmd, bg=CMD_BG)
        inner.pack(fill="x", padx=6, pady=(4, 0))
        command_group(inner, "Файл", [
            ("📄", "Новый", self.file_new),
            ("📂", "Открыть", self.file_open),
            ("💾", "Сохранить", self.file_save),
        ]).pack(side="left")
        v_sep(inner).pack(side="left", fill="y")
        command_group(inner, "Состав", [
            ("📁", "Проект", self.add_project),
            ("🧩", "Сборка", self.add_assembly),
            ("🔧", "Деталь", self.add_part),
            ("✕", "Удалить", self.delete_selected),
        ]).pack(side="left")
        v_sep(inner).pack(side="left", fill="y")
        command_group(inner, "Сервис", [
            ("📚", "Библиотека", self.open_library),
            ("▾", "Развернуть", lambda: self.expand_all(True)),
            ("▸", "Свернуть", lambda: self.expand_all(False)),
        ]).pack(side="left")
        v_sep(inner).pack(side="left", fill="y")
        command_group(inner, "CAD", [
            ("🔗", "Связь", self.open_cad_hub),
            ("⬇", "Файл", self.cad_import_file),
            ("📦", "Папка", self.cad_import_folder),
            ("▣", "Тимц.", self.cad_import_teamcenter),
            ("▶", "В CAD", self.cad_open_selected),
            ("🗂", "Хран.", self.open_node_vault),
        ]).pack(side="left")
        tk.Frame(self.root, bg="#A8B0B8", height=1).pack(fill="x")

        work = tk.Frame(self.root, bg=WORK)
        work.pack(fill="both", expand=True)
        body = ttk.Panedwindow(work, orient="horizontal")
        body.pack(fill="both", expand=True, padx=5, pady=5)

        side = tk.Frame(body, bg=FM_BG, highlightthickness=1, highlightbackground="#8A929A")
        body.add(side, weight=1)
        panel_header(side, "Дерево изделия", FM_HDR, "FeatureManager")
        search_row = tk.Frame(side, bg=FM_BG)
        search_row.pack(fill="x", padx=8, pady=6)
        tk.Label(search_row, text="⌕", bg=FM_BG, fg=DIM, font=("Segoe UI", 11)).pack(side="left")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self.on_search())
        ttk.Entry(search_row, textvariable=self.search_var).pack(side="left", fill="x", expand=True, padx=(6, 0))

        tree_wrap = tk.Frame(side, bg=FM_BG)
        tree_wrap.pack(fill="both", expand=True, padx=1, pady=(0, 1))
        self.tree = ttk.Treeview(tree_wrap, show="tree", selectmode="browse")
        yscroll = ttk.Scrollbar(tree_wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=yscroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        yscroll.pack(side="right", fill="y")
        self.tree.tag_configure("project", font=("Segoe UI", 9, "bold"))
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)
        self.tree.bind("<Button-3>", self.on_tree_menu)
        self.tree.bind("<Delete>", lambda _e: self.delete_selected())

        right = tk.Frame(body, bg=PM_BG, highlightthickness=1, highlightbackground="#8A929A")
        body.add(right, weight=3)
        _bar, self.pm_title, self.pm_sub = panel_header(right, "Свойства", PM_HDR, "Выберите элемент дерева")
        self.crumb = tk.Label(right, text="Нет выбора", bg=PM_BG, fg=DIM, font=("Segoe UI", 8))
        self.crumb.pack(anchor="w", padx=10, pady=(6, 0))

        self.tabs = ttk.Notebook(right)
        self.tabs.pack(fill="both", expand=True, padx=4, pady=4)
        self.tab_data = Scrollable(self.tabs)
        self.tab_check = ttk.Frame(self.tabs, style="PM.TFrame")
        self.tab_bom = ttk.Frame(self.tabs, style="PM.TFrame")
        self.tabs.add(self.tab_data, text="Параметры")
        self.tabs.add(self.tab_check, text="Чек-лист")
        self.tabs.add(self.tab_bom, text="Состав")

        self._build_checklist_tab()
        self._build_bom_tab()

        status = tk.Frame(self.root, bg=STATUS_BG)
        status.pack(fill="x")
        tk.Frame(self.root, bg="#A8B0B8", height=1).pack(fill="x", before=status)
        self.status_ready = tk.Label(status, text="Готово", bg=STATUS_BG, fg=OK, font=("Segoe UI", 8, "bold"))
        self.status_ready.pack(side="left", padx=(10, 12), pady=3)
        tk.Frame(status, bg="#A8B0B8", width=1).pack(side="left", fill="y", pady=4)
        self.status_file = tk.Label(status, text="Файл не сохранён", bg=STATUS_BG, fg=TEXT, font=("Segoe UI", 8))
        self.status_file.pack(side="left", padx=10, pady=3)
        self.status_dirty = tk.Label(status, text="", bg=STATUS_BG, fg=SW_ORANGE, font=("Segoe UI", 8, "bold"))
        self.status_dirty.pack(side="right", padx=10)

        self.ctx = tk.Menu(self.root, tearoff=0)

    def _build_checklist_tab(self):
        top = ttk.Frame(self.tab_check, style="PM.TFrame")
        top.pack(fill="x", padx=8, pady=8)
        self.check_summary = ttk.Label(top, text="", style="Dim.TLabel")
        self.check_summary.pack(side="left")
        ttk.Button(top, text="Сбросить статусы", command=self.reset_checklist).pack(side="right", padx=4)
        ttk.Button(top, text="+ Пункт", command=self.add_check_item).pack(side="right", padx=4)
        ttk.Button(top, text="+ Категория", command=self.add_check_category).pack(side="right", padx=4)
        ttk.Button(top, text="Свой чек-лист", command=self.custom_checklist).pack(side="right", padx=4)
        ttk.Button(top, text="Убрать всё", command=self.clear_checklist).pack(side="right", padx=4)

        wrap = ttk.Frame(self.tab_check, style="PM.TFrame")
        wrap.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        cols = ("status", "comment")
        self.check_tree = ttk.Treeview(wrap, columns=cols, show="tree headings", selectmode="browse")
        self.check_tree.heading("#0", text="Пункт")
        self.check_tree.heading("status", text="Статус")
        self.check_tree.heading("comment", text="Комментарий")
        self.check_tree.column("#0", width=520, stretch=True)
        self.check_tree.column("status", width=160, stretch=False, anchor="center")
        self.check_tree.column("comment", width=220, stretch=True)
        cy = ttk.Scrollbar(wrap, orient="vertical", command=self.check_tree.yview)
        self.check_tree.configure(yscrollcommand=cy.set)
        self.check_tree.pack(side="left", fill="both", expand=True)
        cy.pack(side="right", fill="y")
        self.check_tree.tag_configure("pass", foreground=OK)
        self.check_tree.tag_configure("fail", foreground=DANGER)
        self.check_tree.tag_configure("na", foreground=DIM)
        self.check_tree.tag_configure("pending", foreground=TEXT)
        self.check_tree.tag_configure("cat", font=("Segoe UI", 10, "bold"))
        self.check_tree.bind("<Double-1>", self.on_check_double)
        self.check_tree.bind("<Button-1>", self.on_check_click)

    def _build_bom_tab(self):
        wrap = ttk.Frame(self.tab_bom, style="PM.TFrame")
        wrap.pack(fill="both", expand=True, padx=8, pady=8)
        cols = ("kind", "name", "code", "type", "qty", "cost")
        self.bom_tree = ttk.Treeview(wrap, columns=cols, show="headings", selectmode="browse")
        headings = {
            "kind": "Вид",
            "name": "Наименование",
            "code": "Обозначение",
            "type": "Тип",
            "qty": "Кол-во",
            "cost": "Стоимость, ₽",
        }
        widths = {"kind": 90, "name": 240, "code": 180, "type": 160, "qty": 70, "cost": 120}
        for c in cols:
            self.bom_tree.heading(c, text=headings[c])
            self.bom_tree.column(c, width=widths[c], stretch=c in ("name", "code"))
        by = ttk.Scrollbar(wrap, orient="vertical", command=self.bom_tree.yview)
        self.bom_tree.configure(yscrollcommand=by.set)
        self.bom_tree.pack(side="left", fill="both", expand=True)
        by.pack(side="right", fill="y")
        self.bom_tree.bind("<Double-1>", self.on_bom_open)

    def _bind_keys(self):
        self.root.bind("<Control-n>", lambda _e: self.file_new())
        self.root.bind("<Control-o>", lambda _e: self.file_open())
        self.root.bind("<Control-s>", lambda _e: self.file_save())
        self.root.bind("<Control-S>", lambda _e: self.file_save_as())
        self.root.bind("<Control-Shift-S>", lambda _e: self.file_save_as())

    # ------------------------------------------------------------------ state
    def _set_dirty(self, value: bool):
        self.dirty = value
        mark = "Требуется сохранение" if value else ""
        self.status_dirty.configure(text=mark)
        self.status_ready.configure(text="Изменено" if value else "Готово", fg=SW_ORANGE if value else OK)
        name = self.path.name if self.path else "без имени"
        star = "*" if value else ""
        user = (self.user or {}).get("username") or ""
        who = f" — {user}" if user else ""
        self.root.title(f"{star}{name}{who} — {__app_name__}")

    def mark_dirty(self):
        if self._building:
            return
        self._set_dirty(True)
        self.update_header_cost()
        self.update_status_file()

    def update_status_file(self):
        if self.path:
            self.status_file.configure(text=str(self.path))
        else:
            self.status_file.configure(text="Файл не сохранён")

    def confirm_discard(self) -> bool:
        if not self.dirty:
            return True
        ans = messagebox.askyesnocancel(
            __app_name__,
            "Документ изменён. Сохранить перед продолжением?",
        )
        if ans is None:
            return False
        if ans:
            return self.file_save()
        return True

    # ------------------------------------------------------------------ file
    def _auth_kwargs(self) -> dict:
        name = (self.user or {}).get("username")
        return {"username": name, "key": self._file_key} if name and self._file_key else {}

    def _reset_doc(self, doc: dict) -> dict:
        name = (self.user or {}).get("username")
        vault = ((self.doc or {}).get("vault") or {}).get("root")
        if name:
            doc["owner"] = name
        if vault:
            doc.setdefault("vault", {})["root"] = vault
        return doc

    def file_new(self):
        if not self.confirm_discard():
            return
        self.doc = self._reset_doc(empty_document())
        self.path = None
        self.refresh_all()
        self._set_dirty(False)

    def file_seed(self):
        if not self.confirm_discard():
            return
        self.doc = self._reset_doc(seed_document())
        self.path = None
        self.refresh_all()
        self._set_dirty(True)

    def file_open(self):
        if not self.confirm_discard():
            return
        from .vault import vault_root

        path = filedialog.askopenfilename(
            title="Открыть документ AURA PLM",
            filetypes=JSON_FILTER,
            initialdir=str(self.path.parent) if self.path else str(vault_root(self.doc)),
        )
        if not path:
            return
        try:
            self.doc = load_document(path, **self._auth_kwargs())
        except Exception as exc:
            messagebox.showerror(__app_name__, f"Не удалось открыть файл:\n{exc}")
            return
        self.path = Path(path)
        self.refresh_all()
        self._set_dirty(False)

    def file_import(self):
        from .vault import vault_root

        path = filedialog.askopenfilename(
            title="Импортировать JSON в текущий документ",
            filetypes=JSON_FILTER,
            initialdir=str(self.path.parent) if self.path else str(vault_root(self.doc)),
        )
        if not path:
            return
        try:
            incoming = load_document(path, **self._auth_kwargs())
            merge_document(self.doc, incoming)
        except Exception as exc:
            messagebox.showerror(__app_name__, f"Не удалось импортировать файл:\n{exc}")
            return
        self.refresh_all()
        self.mark_dirty()
        messagebox.showinfo(__app_name__, "Данные добавлены в текущий документ.")

    def file_save(self) -> bool:
        if self.path is None:
            return self.file_save_as()
        return self._write(self.path)

    def file_save_as(self) -> bool:
        path = filedialog.asksaveasfilename(
            title="Сохранить документ AURA PLM",
            defaultextension=".json",
            filetypes=JSON_FILTER,
            initialfile=self.path.name if self.path else "aura-plm.json",
            initialdir=str(self.path.parent) if self.path else str(self.doc.get("vault", {}).get("root") or Path.cwd()),
        )
        if not path:
            return False
        if self._write(Path(path)):
            self.path = Path(path)
            self.update_status_file()
            self._set_dirty(False)
            return True
        return False

    def _write(self, path: Path) -> bool:
        try:
            from .vault import init_vault, vault_root

            init_vault(vault_root(self.doc))
            save_document(path, self.doc, **self._auth_kwargs())
        except Exception as exc:
            messagebox.showerror(__app_name__, f"Не удалось сохранить файл:\n{exc}")
            return False
        self.path = path
        self.update_status_file()
        self._set_dirty(False)
        return True

    def on_close(self):
        if not self.confirm_discard():
            return
        self.root.destroy()

    def change_password(self):
        if not self.user:
            return
        from .auth import change_password as _chg
        from .login import ask_password

        win = tk.Toplevel(self.root)
        win.title("Смена пароля")
        win.configure(bg=WORK)
        win.transient(self.root)
        win.grab_set()
        win.geometry("360x260")
        panel_header(win, "Смена пароля", NAVY, self.user.get("username"))
        frm = ttk.Frame(win, style="PM.TFrame")
        frm.pack(fill="both", expand=True, padx=14, pady=12)
        old_v, new_v, new2_v = tk.StringVar(), tk.StringVar(), tk.StringVar()
        for label, var in (("Текущий пароль", old_v), ("Новый пароль", new_v), ("Ещё раз", new2_v)):
            ttk.Label(frm, text=label, style="Dim.TLabel").pack(anchor="w")
            ttk.Entry(frm, textvariable=var, show="•").pack(fill="x", pady=(0, 8))

        def go():
            if new_v.get() != new2_v.get():
                messagebox.showerror(__app_name__, "Новые пароли не совпадают.", parent=win)
                return
            try:
                rec, key = _chg(self.user["username"], old_v.get(), new_v.get())
            except Exception as exc:
                messagebox.showerror(__app_name__, str(exc), parent=win)
                return
            self.user = rec
            self._file_key = key
            self.mark_dirty()
            win.destroy()
            messagebox.showinfo(__app_name__, "Пароль изменён. Сохраните документ, чтобы перешифровать файл.")

        ttk.Button(frm, text="Сохранить пароль", command=go, style="Accent.TButton").pack(anchor="e")

    def logout(self):
        if not self.confirm_discard():
            return
        from .login import mount_login

        self.user = None
        self._file_key = None
        self.doc = empty_document()
        self.path = None
        self.root.config(menu="")
        for w in self.root.winfo_children():
            w.destroy()
        mount_login(self.root, self._after_login)

    def open_delete_requests(self):
        from .auth import is_admin, list_delete_requests, set_delete_request
        from .login import ask_password
        from .vault import remove_node_storage

        win = tk.Toplevel(self.root)
        win.title("Запросы на удаление")
        win.geometry("720x400")
        win.transient(self.root)
        win.configure(bg=WORK)
        cols = ("who", "what", "kind", "when", "status")
        table = ttk.Treeview(win, columns=cols, show="headings", height=12)
        for c, h, wdt in (
            ("who", "Кто", 120),
            ("what", "Что", 220),
            ("kind", "Вид", 80),
            ("when", "Когда", 130),
            ("status", "Статус", 100),
        ):
            table.heading(c, text=h)
            table.column(c, width=wdt)
        table.pack(fill="both", expand=True, padx=8, pady=8)

        def reload():
            table.delete(*table.get_children())
            for r in list_delete_requests(None):
                table.insert("", "end", iid=r["id"], values=(
                    r.get("username") or "",
                    r.get("title") or "",
                    r.get("kind") or "",
                    r.get("created") or "",
                    r.get("status") or "",
                ))

        def approve():
            if not is_admin(self.user):
                messagebox.showinfo(__app_name__, "Одобряет только администратор PLM.")
                return
            sel = table.selection()
            if not sel:
                return
            user = (self.user or {}).get("username") or ""
            if not ask_password(self.root, user, "Одобрение удаления"):
                return
            req = set_delete_request(sel[0], "approved")
            if not req:
                return
            prj = find_project(self.doc, req.get("projectId"))
            kind = req.get("kind")
            node = None
            if kind == "project":
                node = prj
            elif kind == "assembly" and prj:
                node = find_assembly(self.doc, prj["id"], req.get("assemblyId"))
            elif kind == "part" and prj:
                asm = find_assembly(self.doc, prj["id"], req.get("assemblyId"))
                node = find_part_in_assembly(asm, req.get("partId")) if asm else None
            if prj and node:
                remove_node_storage(self.doc, prj, node, kind)
                delete_node(self.doc, kind, req.get("projectId"), req.get("assemblyId"), req.get("partId"))
                self.mark_dirty()
                self.refresh_all()
            reload()

        def deny():
            if not is_admin(self.user):
                messagebox.showinfo(__app_name__, "Отклоняет только администратор PLM.")
                return
            sel = table.selection()
            if not sel:
                return
            req = set_delete_request(sel[0], "denied")
            if req and req.get("nodeId"):
                prj = find_project(self.doc, req.get("projectId"))
                node = None
                if req.get("kind") == "project":
                    node = prj
                elif req.get("kind") == "assembly" and prj:
                    node = find_assembly(self.doc, prj["id"], req.get("assemblyId"))
                elif req.get("kind") == "part" and prj:
                    asm = find_assembly(self.doc, prj["id"], req.get("assemblyId"))
                    node = find_part_in_assembly(asm, req.get("partId")) if asm else None
                if node:
                    node["pendingDelete"] = False
                    self.mark_dirty()
                    self.rebuild_tree()
            reload()

        btns = ttk.Frame(win)
        btns.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(btns, text="Одобрить и удалить файлы", command=approve).pack(side="left", padx=(0, 6))
        ttk.Button(btns, text="Отклонить", command=deny).pack(side="left")
        reload()

    def open_cad_hub(self):
        open_cad_hub(self)

    def cad_import_file(self):
        from .cad_ui import _run_import

        path = filedialog.askopenfilename(
            title="Выгрузить сборку или деталь из CAD",
            filetypes=file_dialog_filter(),
        )
        if path:
            _run_import(self, path, None, self.root)

    def cad_import_folder(self):
        from .cad_ui import _run_import

        path = filedialog.askdirectory(title="Папка проекта CAD")
        if path:
            _run_import(self, path, None, self.root)

    def cad_grab_running(self):
        from .cad_ui import _accept_project

        systems = detect_cad_systems()
        running = [s for s in systems if s.get("running") and s.get("id") != "step"]
        if not running:
            messagebox.showinfo(
                __app_name__,
                "Не найдена запущенная CAD.\nОткройте SolidWorks, КОМПАС-3D, Inventor или AutoCAD,\nсохраните документ и повторите.",
            )
            return
        sid = running[0]["id"]
        if sid == "teamcenter":
            self.cad_import_teamcenter()
            return
        from .cad.live import GrabError, file_filter_for
        from .cad_ui import import_teamcenter_into, _run_import

        try:
            prj = import_from_running_cad(sid)
        except GrabError as exc:
            if exc.managed:
                choice = messagebox.askyesnocancel(
                    __app_name__,
                    str(exc) + "\n\nДа — выгрузить PLMXML из Teamcenter\nНет — указать файл на диске",
                )
                if choice is None:
                    return
                if choice:
                    import_teamcenter_into(self, self.root)
                    return
            path = filedialog.askopenfilename(
                title="Укажите сохранённую сборку на диске",
                filetypes=file_filter_for(sid),
            )
            if path:
                _run_import(self, path, sid, self.root)
            return
        except Exception as exc:
            messagebox.showerror(__app_name__, str(exc))
            return
        _accept_project(self, prj, sid, prj.get("cadSource") or "", self.root)

    def cad_import_teamcenter(self):
        from .cad_ui import import_teamcenter_into

        import_teamcenter_into(self, self.root)

    def current_project(self):
        sel = self.doc.get("selection") or {}
        if sel.get("projectId"):
            return find_project(self.doc, sel["projectId"])
        return None

    def choose_vault(self):
        from .auth import is_admin
        from .vault import init_vault, set_vault_root, vault_root

        if not is_admin(self.user):
            messagebox.showinfo(__app_name__, "Папку хранилища меняет только администратор PLM.")
            return
        current = vault_root(self.doc)
        path = filedialog.askdirectory(title="Папка хранилища AURA PLM", initialdir=str(current))
        if not path:
            return
        set_vault_root(self.doc, path)
        init_vault(path)
        self.mark_dirty()
        messagebox.showinfo(__app_name__, f"Хранилище:\n{path}")

    def open_vault_folder(self):
        from .vault import init_vault, vault_root
        from .cad.importing import reveal_in_explorer

        root = init_vault(vault_root(self.doc))
        reveal_in_explorer(root)

    def open_node_vault(self):
        from .vault import ensure_node_storage
        from .cad.importing import reveal_in_explorer

        kind, node = self.current_node()
        prj = self.current_project()
        if not node or not prj:
            self.open_vault_folder()
            return
        folder = ensure_node_storage(self.doc, prj, node, kind)
        reveal_in_explorer(folder)

    def cad_open_selected(self):
        kind, node = self.current_node()
        prj = self.current_project()
        if not node:
            messagebox.showinfo(__app_name__, "Выберите сборку или деталь в дереве.")
            return
        if prj and kind:
            from .vault import open_node_in_cad

            try:
                open_node_in_cad(self.doc, prj, node, kind)
            except Exception as exc:
                messagebox.showerror(__app_name__, str(exc))
            return
        open_node_cad(self, node)

    def open_cart(self):
        from .cart_ui import open_cart_window

        open_cart_window(self)

    def update_cart_badge(self):
        from .cart import cart_count

        n = len(self.doc.get("cart") or [])
        qty = cart_count(self.doc)
        if getattr(self, "_cart_badge", None):
            self._cart_badge.configure(text=str(qty if n else "0"))
        if getattr(self, "_cart_win", None) and self._cart_win.winfo_exists():
            from .cart_ui import _fill

            _fill(self)

    def add_selected_to_cart(self):
        from .cart import add_node_to_cart

        ref = self.current_ref()
        if not ref or ref[0] == "project":
            messagebox.showinfo(__app_name__, "В корзину добавляют сборку или деталь.")
            return
        kind, prj_id, asm_id, part_id = ref
        try:
            msg = add_node_to_cart(self.doc, kind, prj_id, asm_id, part_id, 1)
        except Exception as exc:
            messagebox.showinfo(__app_name__, str(exc))
            return
        self.mark_dirty()
        self.update_cart_badge()
        messagebox.showinfo(__app_name__, msg)

    def export_hierarchy_excel(self):
        from .excel_export import default_hierarchy_xlsx_name, export_hierarchy_csv, export_hierarchy_xlsx

        prj = self.current_project()
        if not prj:
            messagebox.showinfo(__app_name__, "Сначала выберите проект.")
            return
        path = filedialog.asksaveasfilename(
            title="Экспорт иерархии в Excel",
            defaultextension=".xlsx",
            initialfile=default_hierarchy_xlsx_name(prj),
            filetypes=[("Excel", "*.xlsx"), ("CSV", "*.csv")],
        )
        if not path:
            return
        dest = Path(path)
        try:
            if dest.suffix.lower() == ".csv":
                export_hierarchy_csv(prj, dest)
            else:
                try:
                    export_hierarchy_xlsx(prj, dest)
                except ImportError:
                    dest = dest.with_suffix(".csv")
                    export_hierarchy_csv(prj, dest)
                    messagebox.showinfo(__app_name__, f"openpyxl не установлен, сохранён CSV:\n{dest}")
                    return
        except Exception as exc:
            messagebox.showerror(__app_name__, str(exc))
            return
        messagebox.showinfo(__app_name__, f"Сохранено:\n{dest}")

    def export_cart_excel(self):
        from .excel_export import default_cart_xlsx_name, export_cart_csv, export_cart_xlsx

        if not (self.doc.get("cart") or []):
            messagebox.showinfo(__app_name__, "Корзина пуста.")
            return
        path = filedialog.asksaveasfilename(
            title="Экспорт корзины в Excel",
            defaultextension=".xlsx",
            initialfile=default_cart_xlsx_name(),
            filetypes=[("Excel", "*.xlsx"), ("CSV", "*.csv")],
        )
        if not path:
            return
        dest = Path(path)
        try:
            if dest.suffix.lower() == ".csv":
                export_cart_csv(self.doc, dest)
            else:
                try:
                    export_cart_xlsx(self.doc, dest)
                except ImportError:
                    dest = dest.with_suffix(".csv")
                    export_cart_csv(self.doc, dest)
                    messagebox.showinfo(__app_name__, f"openpyxl не установлен, сохранён CSV:\n{dest}")
                    return
        except Exception as exc:
            messagebox.showerror(__app_name__, str(exc))
            return
        messagebox.showinfo(__app_name__, f"Сохранено:\n{dest}")

    def cad_open_with(self):
        kind, node = self.current_node()
        prj = self.current_project()
        if not node or not prj:
            messagebox.showinfo(__app_name__, "Выберите сборку или деталь.")
            return
        systems = [s for s in detect_cad_systems() if s.get("installed") and s.get("id") not in {"step", "teamcenter"}]
        if not systems:
            messagebox.showinfo(__app_name__, "Установленная CAD не найдена.")
            return
        win = tk.Toplevel(self.root)
        win.title("Открыть в CAD")
        win.configure(bg=PM_BG)
        win.transient(self.root)
        win.geometry("360x320")
        panel_header(win, "Запуск CAD", PM_HDR, "из хранилища AURA")
        frm = ttk.Frame(win, style="PM.TFrame")
        frm.pack(fill="both", expand=True, padx=12, pady=10)
        ttk.Label(frm, text="Система:", style="Dim.TLabel").pack(anchor="w")
        lst = tk.Listbox(frm, font=("Segoe UI", 10), height=10)
        lst.pack(fill="both", expand=True, pady=6)
        for s in systems:
            mark = " ●" if s.get("running") else ""
            lst.insert("end", f"{s['name']}{mark}")
        lst.selection_set(0)

        def go():
            sel = lst.curselection()
            if not sel:
                return
            sid = systems[sel[0]]["id"]
            from .vault import open_node_in_cad

            try:
                open_node_in_cad(self.doc, prj, node, kind, sid)
            except Exception as exc:
                messagebox.showerror(__app_name__, str(exc), parent=win)
            win.destroy()

        ttk.Button(frm, text="Открыть", command=go, style="Accent.TButton").pack(anchor="e")

    def show_about(self):
        messagebox.showinfo(
            "О программе",
            f"{__app_name__}  v{__version__}\n\n"
            "Оконный PLM-менеджер состава изделия.\n"
            "Проект → сборка → деталь, чек-листы, библиотека.\n"
            "Связь с CAD: SolidWorks, КОМПАС-3D, Inventor, STEP и другие.\n"
            "Документы сохраняются в JSON, шифруются ключом аккаунта.\n"
            "Хранилище файлов — отдельно на каждого пользователя.",
        )

    # ------------------------------------------------------------------ tree
    def on_search(self):
        self.search_query = self.search_var.get().strip()
        self.rebuild_tree()

    def refresh_all(self):
        self.rebuild_tree()
        self.show_selection()
        self.update_header_cost()
        self.update_status_file()
        self.update_cart_badge()

    def rebuild_tree(self):
        opened = set()

        def collect(iid=""):
            for child in self.tree.get_children(iid):
                if self.tree.item(child, "open"):
                    opened.add(child)
                collect(child)

        collect()
        selected = list(self.tree.selection())
        self.tree.delete(*self.tree.get_children())
        self._index.clear()
        query = self.search_query

        for prj in self.doc.get("projects") or []:
            if query and not project_matches(prj, query):
                continue
            pid = prj["id"]
            self._index[pid] = ("project", pid, None, None)
            self.tree.insert(
                "",
                "end",
                iid=pid,
                text=f"{KIND_ICONS['project']}  {tree_label('project', prj)}"
                + ("  ⚠ на удаление" if prj.get("pendingDelete") else ""),
                tags=("project",),
                open=prj.get("expanded", True) or bool(query) or pid in opened,
            )
            asms = prj.get("assemblies") or []
            if query:
                asms = [a for a in asms if assembly_matches(a, query)]
            for asm in asms:
                self._insert_assembly(pid, pid, asm, query, opened)

        want = None
        sel = self.doc.get("selection") or {}
        if sel.get("partId"):
            want = sel["partId"]
        elif sel.get("assemblyId"):
            want = sel["assemblyId"]
        elif sel.get("projectId"):
            want = sel["projectId"]
        if selected and self.tree.exists(selected[0]):
            want = selected[0]
        if want and self.tree.exists(want):
            self.tree.selection_set(want)
            self.tree.see(want)

    def _insert_assembly(self, parent_iid, project_id, asm, query, opened):
        aid = asm["id"]
        self._index[aid] = ("assembly", project_id, aid, None)
        open_it = asm.get("expanded", True) or bool(query) or aid in opened
        self.tree.insert(
            parent_iid,
            "end",
            iid=aid,
            text=f"{KIND_ICONS['assembly']}  {tree_label('assembly', asm)}"
            + ("  ⚠ на удаление" if asm.get("pendingDelete") else ""),
            tags=("assembly",),
            open=open_it,
        )
        nested = asm.get("assemblies") or []
        parts = asm.get("parts") or []
        if query:
            nested = [a for a in nested if assembly_matches(a, query)]
            parts = [p for p in parts if node_matches(p, query)]
        for nested_asm in nested:
            self._insert_assembly(aid, project_id, nested_asm, query, opened)
        for part in parts:
            pid = part["id"]
            self._index[pid] = ("part", project_id, aid, pid)
            self.tree.insert(
                aid,
                "end",
                iid=pid,
                text=f"{KIND_ICONS['part']}  {tree_label('part', part)}"
                + ("  ⚠ на удаление" if part.get("pendingDelete") else ""),
                tags=("part",),
            )

    def current_ref(self):
        sel = self.tree.selection()
        if not sel:
            return None
        return self._index.get(sel[0])

    def current_node(self):
        ref = self.current_ref()
        if not ref:
            return None, None
        kind, prj_id, asm_id, part_id = ref
        if kind == "project":
            return kind, find_project(self.doc, prj_id)
        if kind == "assembly":
            return kind, find_assembly(self.doc, prj_id, asm_id)
        prj = find_project(self.doc, prj_id)
        asm = find_assembly(self.doc, prj_id, asm_id) if prj else None
        part = find_part_in_assembly(asm, part_id) if asm else None
        return kind, part

    def on_tree_select(self, _event=None):
        if self._building:
            return
        ref = self.current_ref()
        if not ref:
            self.doc["selection"] = {"type": None, "projectId": None, "assemblyId": None, "partId": None}
        else:
            kind, prj_id, asm_id, part_id = ref
            self.doc["selection"] = {
                "type": kind,
                "projectId": prj_id,
                "assemblyId": asm_id,
                "partId": part_id,
            }
        self.show_selection()
        self.update_header_cost()

    def on_tree_menu(self, event):
        row = self.tree.identify_row(event.y)
        if row:
            self.tree.selection_set(row)
        self.ctx.delete(0, "end")
        self.ctx.add_command(label="Новый проект", command=self.add_project)
        self.ctx.add_command(label="Добавить сборку", command=self.add_assembly)
        self.ctx.add_command(label="Создать деталь в CAD…", command=self.create_part_in_cad)
        self.ctx.add_command(label="Добавить деталь", command=self.add_part)
        self.ctx.add_separator()
        self.ctx.add_command(label="В корзину покупнины", command=self.add_selected_to_cart)
        self.ctx.add_separator()
        self.ctx.add_command(label="Дублировать", command=self.duplicate_selected)
        self.ctx.add_command(label="Удалить", command=self.delete_selected)
        self.ctx.tk_popup(event.x_root, event.y_root)

    def expand_all(self, opened: bool):
        def walk(iid=""):
            for child in self.tree.get_children(iid):
                self.tree.item(child, open=opened)
                walk(child)

        walk()

    def add_project(self):
        prj = new_project("Новый проект")
        self.doc.setdefault("projects", []).append(prj)
        from .vault import ensure_node_storage

        ensure_node_storage(self.doc, prj, prj, "project")
        self.mark_dirty()
        self.rebuild_tree()
        if self.tree.exists(prj["id"]):
            self.tree.selection_set(prj["id"])
            self.on_tree_select()

    def add_assembly(self):
        ref = self.current_ref()
        if not ref:
            messagebox.showinfo(__app_name__, "Сначала выберите проект или сборку.")
            return
        kind, prj_id, asm_id, _part_id = ref
        parent = None
        if kind == "project":
            parent = find_project(self.doc, prj_id)
            bucket = "assemblies"
        elif kind in ("assembly", "part"):
            parent = find_assembly(self.doc, prj_id, asm_id)
            bucket = "assemblies"
        else:
            return
        if parent is None:
            return
        asm = new_assembly("Новая сборка")
        parent.setdefault(bucket, []).append(asm)
        parent["expanded"] = True
        prj = find_project(self.doc, prj_id)
        if prj:
            from .vault import ensure_node_storage

            ensure_node_storage(self.doc, prj, asm, "assembly")
        self.mark_dirty()
        self.rebuild_tree()
        if self.tree.exists(asm["id"]):
            self.tree.selection_set(asm["id"])
            self.on_tree_select()

    def add_part(self):
        self.create_part_in_cad()

    def create_part_in_cad(self):
        from .cad.detect import authoring_cad_systems
        from .cad.systems import get_system
        from .vault import ensure_node_storage, launch_cad

        ref = self.current_ref()
        if not ref or ref[0] == "project":
            messagebox.showinfo(__app_name__, "Выберите сборку или деталь — новая деталь попадёт в эту сборку.")
            return
        kind, prj_id, asm_id, _part_id = ref
        asm = find_assembly(self.doc, prj_id, asm_id)
        prj = find_project(self.doc, prj_id)
        if not asm or not prj:
            return
        cads = authoring_cad_systems()
        win = tk.Toplevel(self.root)
        win.title("Создать деталь в CAD")
        win.configure(bg=WORK)
        win.geometry("480x520")
        win.transient(self.root)
        win.grab_set()
        panel_header(win, "Новая деталь", PM_HDR, "выбор CAD на этом компьютере")
        frm = ttk.Frame(win, style="PM.TFrame")
        frm.pack(fill="both", expand=True, padx=14, pady=12)
        name_v = tk.StringVar(value="Новая деталь")
        des_v = tk.StringVar()
        ttk.Label(frm, text="Наименование", style="Dim.TLabel").pack(anchor="w")
        ttk.Entry(frm, textvariable=name_v).pack(fill="x", pady=(0, 8))
        ttk.Label(frm, text="Обозначение", style="Dim.TLabel").pack(anchor="w")
        ttk.Entry(frm, textvariable=des_v).pack(fill="x", pady=(0, 10))
        ttk.Label(frm, text="Создать модель в программе:", style="Dim.TLabel").pack(anchor="w")
        cad_id = tk.StringVar(value=cads[0]["id"] if cads else "none")
        box = ttk.Frame(frm, style="PM.TFrame")
        box.pack(fill="both", expand=True, pady=(4, 8))
        if not cads:
            ttk.Label(box, text="На компьютере не найдена CAD (SolidWorks, NX, КОМПАС и др.).\nДеталь будет только в AURA.", style="Dim.TLabel", wraplength=420).pack(anchor="w")
            cad_id.set("none")
        else:
            for s in cads:
                extra = "  · запущена" if s.get("running") else "  · установлена"
                ttk.Radiobutton(box, text=f"{s['name']}{extra}", variable=cad_id, value=s["id"]).pack(anchor="w", pady=2)
        ttk.Radiobutton(box, text="Только в AURA, без запуска CAD", variable=cad_id, value="none").pack(anchor="w", pady=(8, 2))

        def go():
            part = new_part(name_v.get().strip() or "Новая деталь")
            part["designation"] = des_v.get().strip()
            sid = cad_id.get()
            if sid and sid != "none":
                part["cadSystem"] = sid
            asm.setdefault("parts", []).append(part)
            asm["expanded"] = True
            folder = ensure_node_storage(self.doc, prj, part, "part")
            native = folder / "native"
            native.mkdir(parents=True, exist_ok=True)
            sys = get_system(sid) if sid != "none" else None
            ext = (sys.part_ext[0] if sys and sys.part_ext else "")
            stem = part["designation"] or part["name"]
            hint = native / "СОХРАНИТЕ_МОДЕЛЬ_СЮДА.txt"
            hint.write_text(
                f"Деталь AURA: {part['name']}\n"
                f"Обозначение: {part.get('designation') or '—'}\n"
                f"CAD: {sys.name if sys else 'не выбран'}\n\n"
                f"Сохраните файл в эту папку"
                + (f" как «{stem}{ext}».\n" if ext else ".\n"),
                encoding="utf-8",
            )
            self.mark_dirty()
            self.rebuild_tree()
            if self.tree.exists(part["id"]):
                self.tree.selection_set(part["id"])
                self.on_tree_select()
            win.destroy()
            if sid != "none":
                try:
                    launch_cad(sid, native)
                except Exception as exc:
                    messagebox.showerror(__app_name__, str(exc))
                    return
                messagebox.showinfo(
                    __app_name__,
                    f"Деталь «{part['name']}» создана в сборке «{asm.get('name')}».\n"
                    f"Открыт {sys.name if sys else 'CAD'}.\n"
                    f"Сохраните модель в:\n{native}",
                )

        ttk.Button(frm, text="Создать и открыть CAD", command=go, style="Accent.TButton").pack(anchor="e", pady=(4, 0))

    def delete_selected(self):
        ref = self.current_ref()
        if not ref:
            return
        kind, prj_id, asm_id, part_id = ref
        _, node = self.current_node()
        if not node:
            return
        title = node.get("name") or kind
        from .auth import add_delete_request, is_admin
        from .login import ask_password
        from .vault import node_dir, remove_node_storage

        prj = find_project(self.doc, prj_id)
        vault_folder = ""
        if prj:
            try:
                vault_folder = str(node_dir(self.doc, prj, node, kind))
            except Exception:
                vault_folder = node.get("vaultPath") or ""

        if is_admin(self.user):
            if not messagebox.askyesno(__app_name__, f"Удалить «{title}» и файлы из хранилища?"):
                return
            user = (self.user or {}).get("username") or ""
            if not ask_password(self.root, user, "Удаление из хранилища"):
                return
            if prj:
                remove_node_storage(self.doc, prj, node, kind)
            if delete_node(self.doc, kind, prj_id, asm_id, part_id):
                self.doc["selection"] = {"type": None, "projectId": None, "assemblyId": None, "partId": None}
                self.mark_dirty()
                self.refresh_all()
            return

        if not messagebox.askyesno(
            __app_name__,
            f"Файлы «{title}» в хранилище удаляет только администратор.\n"
            "Отправить запрос на удаление?",
        ):
            return
        node["pendingDelete"] = True
        add_delete_request(
            (self.user or {}).get("username") or "",
            {
                "title": title,
                "kind": kind,
                "nodeId": node.get("id"),
                "projectId": prj_id,
                "assemblyId": asm_id,
                "partId": part_id,
                "vaultPath": vault_folder,
            },
        )
        self.mark_dirty()
        self.rebuild_tree()
        messagebox.showinfo(__app_name__, "Запрос отправлен администратору. Файлы хранилища не тронуты.")

    def duplicate_selected(self):
        ref = self.current_ref()
        if not ref:
            return
        kind, prj_id, asm_id, part_id = ref
        if kind == "project":
            src = find_project(self.doc, prj_id)
            if not src:
                return
            clone = duplicate_node(src, "project")
            self.doc["projects"].append(clone)
            new_id = clone["id"]
        elif kind == "assembly":
            prj = find_project(self.doc, prj_id)
            src = find_assembly(self.doc, prj_id, asm_id)
            if not prj or not src:
                return
            from .model import parent_of_assembly

            loc = parent_of_assembly(prj, asm_id)
            if not loc:
                return
            parent, list_name = loc
            clone = duplicate_node(src, "assembly")
            parent[list_name].append(clone)
            new_id = clone["id"]
        else:
            prj = find_project(self.doc, prj_id)
            src_asm = find_assembly(self.doc, prj_id, asm_id)
            src = find_part_in_assembly(src_asm, part_id) if src_asm else None
            if not prj or not src or not src_asm:
                return
            clone = duplicate_node(src, "part")
            src_asm.setdefault("parts", []).append(clone)
            new_id = clone["id"]
        self.mark_dirty()
        self.rebuild_tree()
        if self.tree.exists(new_id):
            self.tree.selection_set(new_id)
            self.on_tree_select()

    def update_header_cost(self):
        sel = self.doc.get("selection") or {}
        prj = find_project(self.doc, sel.get("projectId")) if sel.get("projectId") else None
        if not prj and len(self.doc.get("projects") or []) == 1:
            prj = self.doc["projects"][0]
        if not prj:
            self.header_cost.configure(text="—")
            return
        total = project_total_cost(prj)
        self.header_cost.configure(text=f"{format_money(total)} ₽")

    # ------------------------------------------------------------------ details
    def show_selection(self):
        kind, node = self.current_node()
        self._stop_preview()
        self.tab_data.clear()
        if not kind or not node:
            ttk.Label(
                self.tab_data.body,
                text="Выберите элемент в дереве изделия\nили создайте новый проект на панели Command Manager.",
                style="Dim.TLabel",
                justify="center",
            ).pack(pady=80)
            self.crumb.configure(text="Нет выбора")
            self.pm_title.configure(text="Свойства")
            self.pm_sub.configure(text="Выберите элемент дерева")
            self._fill_checklist(None)
            self._fill_bom(None, None)
            return

        self._building = True
        try:
            crumb = self._breadcrumb()
            self.crumb.configure(text=crumb)
            self.pm_title.configure(text=f"{KIND_TITLES.get(kind, 'Свойства')}:  {node.get('name') or ''}")
            self.pm_sub.configure(text=KIND_TITLES.get(kind, ""))
            if kind == "project":
                self._form_project(node)
            elif kind == "assembly":
                self._form_assembly(node)
            else:
                self._form_part(node)
            self._fill_checklist(node)
            self._fill_bom(kind, node)
        finally:
            self._building = False

    def _breadcrumb(self) -> str:
        sel = self.doc.get("selection") or {}
        parts = []
        prj = find_project(self.doc, sel.get("projectId")) if sel.get("projectId") else None
        if prj:
            parts.append(f"📁 {prj.get('name')}")
        if sel.get("assemblyId") and prj:
            asm = find_assembly(self.doc, prj["id"], sel["assemblyId"])
            if asm:
                parts.append(f"🧩 {asm.get('name')}")
        if sel.get("partId") and prj and sel.get("assemblyId"):
            asm = find_assembly(self.doc, prj["id"], sel["assemblyId"])
            part = find_part_in_assembly(asm, sel["partId"]) if asm else None
            if part:
                parts.append(f"🔧 {part.get('name')}")
        return "  ›  ".join(parts) if parts else ""

    def _card(self, parent, title: str) -> ttk.Frame:
        outer = tk.Frame(parent, bg=PM_GROUP, highlightthickness=1, highlightbackground=PM_BORDER)
        outer.pack(fill="x", padx=8, pady=6)
        hdr = tk.Frame(outer, bg=PM_GROUP_HDR)
        hdr.pack(fill="x")
        tk.Label(hdr, text=f"  {title}", bg=PM_GROUP_HDR, fg="#FFFFFF", font=("Segoe UI", 9, "bold"), anchor="w").pack(
            fill="x", ipady=4
        )
        inner = ttk.Frame(outer, style="Card.TFrame")
        inner.pack(fill="x", padx=12, pady=10)
        return inner

    def _stop_preview(self):
        if self._preview_job:
            try:
                self.root.after_cancel(self._preview_job)
            except tk.TclError:
                pass
            self._preview_job = None
        self._preview_images = []

    def _preview_column(self, parent, node: dict, kind: str):
        box = tk.Frame(parent, bg="#1A2330", width=188, height=210, highlightthickness=1, highlightbackground=PM_BORDER)
        box.pack()
        box.pack_propagate(False)
        icon = placeholder_icon(kind)
        cv = tk.Canvas(box, bg="#1A2330", highlightthickness=0, width=186, height=208, cursor="hand2")
        cv.pack(fill="both", expand=True)
        photo = node_photo_path(node)
        model = node_model_path(node)
        if photo:
            try:
                single, frames, durs = load_preview(photo)
            except Exception:
                single, frames, durs = None, [], []
            if single:
                self._preview_images = frames
                img_id = cv.create_image(93, 104, image=single)
                cv.image = single
                if len(frames) > 1:
                    self._cycle_gif_canvas(cv, img_id, frames, durs, 0)
                cv.bind("<Button-1>", lambda _e, p=photo: self._photo_lightbox(p))
            else:
                cv.create_text(93, 104, text=icon, fill="#8AA0B5", font=("Segoe UI", 42))
        else:
            cv.create_text(93, 104, text=icon, fill="#8AA0B5", font=("Segoe UI", 42), tags="ph")
            if model:
                self._fill_model_thumb(cv, model)
                cv.bind("<Button-1>", lambda _e, n=node: self._open_node_3d(n))
            else:
                cv.bind("<Button-1>", lambda _e, n=node: self._open_node_3d(n))
        btns = ttk.Frame(parent, style="Card.TFrame")
        btns.pack(fill="x", pady=(8, 0))

        def pick_photo():
            path = filedialog.askopenfilename(
                title="Фото / GIF",
                filetypes=[("Изображения", "*.png;*.jpg;*.jpeg;*.gif;*.bmp;*.webp"), ("Все файлы", "*.*")],
            )
            if not path:
                return
            prj = self.current_project()
            if prj:
                from .vault import ingest_file

                ingest_file(self.doc, prj, node, kind, path, as_photo=True)
            else:
                node["photo"] = str(Path(path).resolve())
            self.mark_dirty()
            self.show_selection()

        def clear_photo():
            node["photo"] = ""
            self.mark_dirty()
            self.show_selection()

        def open_3d():
            self._open_node_3d(node)

        tk.Button(
            btns, text="📷  Фото / GIF", command=pick_photo,
            bg=SW_BLUE, fg="#fff", relief="flat", font=("Segoe UI", 9, "bold"),
            activebackground="#1A7FBF", activeforeground="#fff", cursor="hand2",
        ).pack(fill="x", pady=(0, 4), ipady=4)
        model = node_model_path(node)
        tk.Button(
            btns, text="🧊  3D STEP / STL", command=open_3d,
            bg="#0A84FF" if model else "#8AA0B5", fg="#fff", relief="flat",
            font=("Segoe UI", 9, "bold"),
            activebackground="#1A7FBF", activeforeground="#fff", cursor="hand2",
        ).pack(fill="x", ipady=4)
        ttk.Button(btns, text="Папка хранилища", command=self.open_node_vault).pack(fill="x", pady=(4, 0))
        if kind in {"assembly", "part"}:
            ttk.Button(btns, text="Создать деталь в CAD…", command=self.create_part_in_cad).pack(fill="x", pady=(4, 0))
        if photo:
            ttk.Button(btns, text="Убрать фото", command=clear_photo).pack(fill="x", pady=(4, 0))

    def _cycle_gif(self, label, frames, durs, i):
        if not frames or not label.winfo_exists():
            return
        frame = frames[i % len(frames)]
        label.configure(image=frame)
        delay = durs[i % len(durs)] if durs else 100
        self._preview_job = self.root.after(delay, lambda: self._cycle_gif(label, frames, durs, i + 1))

    def _cycle_gif_canvas(self, canvas, img_id, frames, durs, i):
        if not frames or not canvas.winfo_exists():
            return
        canvas.itemconfigure(img_id, image=frames[i % len(frames)])
        delay = durs[i % len(durs)] if durs else 100
        self._preview_job = self.root.after(
            delay, lambda: self._cycle_gif_canvas(canvas, img_id, frames, durs, i + 1)
        )

    def _fill_model_thumb(self, canvas, model: Path):
        def paint(tris):
            if not canvas.winfo_exists() or not tris:
                return
            canvas.delete("ph")
            draw_mesh_preview(canvas, tris)

        hit = cached_mesh_path(model)
        if hit:
            try:
                paint(load_stl(hit))
                return
            except Exception:
                pass

        def work():
            try:
                tris = load_model(model)
            except Exception:
                return
            self.root.after(0, lambda: paint(tris))

        threading.Thread(target=work, daemon=True).start()

    def _photo_lightbox(self, path: Path):
        win = tk.Toplevel(self.root)
        win.title(path.name)
        win.configure(bg="#111")
        try:
            single, frames, durs = load_preview(path, size=(900, 700))
        except Exception as exc:
            messagebox.showerror(__app_name__, str(exc), parent=win)
            win.destroy()
            return
        if not single:
            messagebox.showinfo(__app_name__, "Не удалось открыть изображение.", parent=win)
            win.destroy()
            return
        lbl = tk.Label(win, image=single, bg="#111")
        lbl.image = single
        lbl.pack()
        win._frames = frames
        if len(frames) > 1:
            def cycle(i=0):
                if not lbl.winfo_exists():
                    return
                lbl.configure(image=frames[i % len(frames)])
                win.after(durs[i % len(durs)], lambda: cycle(i + 1))
            cycle(0)

    def _open_node_3d(self, node: dict):
        path = node_model_path(node)
        if path is None:
            picked = filedialog.askopenfilename(
                title="3D STEP / STL",
                filetypes=[
                    ("STEP / STL", "*.step;*.stp;*.stl"),
                    ("STEP", "*.step;*.stp"),
                    ("STL", "*.stl"),
                    ("Все файлы", "*.*"),
                ],
            )
            if not picked:
                return
            path = Path(picked)
            prj = self.current_project()
            if prj:
                from .vault import ingest_file

                kind, _n = self.current_node()
                ingest_file(self.doc, prj, node, kind or "part", path)
            else:
                attach_cad_file(node, path)
            self.mark_dirty()
        try:
            open_model(self.root, path, node.get("name") or path.name)
        except Exception as exc:
            messagebox.showerror(__app_name__, f"Не удалось открыть 3D:\n{exc}")
        self.show_selection()

    def _bind_str(self, var: tk.StringVar, node: dict, key: str, refresh_tree=False):
        def on_write(*_):
            if self._building:
                return
            node[key] = var.get()
            self.mark_dirty()
            if refresh_tree:
                iid = node.get("id")
                if iid and self.tree.exists(iid):
                    info = self._index.get(iid)
                    k = info[0] if info else "part"
                    icon = KIND_ICONS.get(k, "")
                    self.tree.item(iid, text=f"{icon}  {tree_label(k, node)}")
                    self.crumb.configure(text=self._breadcrumb())
                    self.update_header_cost()

        var.trace_add("write", on_write)

    def _bind_num(self, var: tk.StringVar, node: dict, key: str, as_int=False, min_value=0):
        def on_write(*_):
            if self._building:
                return
            raw = var.get().replace(",", ".").strip()
            try:
                value = int(float(raw)) if as_int else float(raw)
            except ValueError:
                return
            if value < min_value:
                value = min_value
            node[key] = value
            self.mark_dirty()
            self.update_header_cost()

        var.trace_add("write", on_write)

    def _field(self, parent, label, var, width=None):
        box = ttk.Frame(parent, style="Card.TFrame")
        box.pack(fill="x", pady=4)
        ttk.Label(box, text=label, style="CardDim.TLabel").pack(anchor="w")
        entry = ttk.Entry(box, textvariable=var)
        entry.pack(fill="x", pady=(2, 0))
        return entry

    def _combo(self, parent, label, var, values):
        box = ttk.Frame(parent, style="Card.TFrame")
        box.pack(fill="x", pady=4)
        ttk.Label(box, text=label, style="CardDim.TLabel").pack(anchor="w")
        cb = ttk.Combobox(box, textvariable=var, values=values, state="normal")
        cb.pack(fill="x", pady=(2, 0))
        return cb

    def _grid_pair(self, parent):
        row = ttk.Frame(parent, style="Card.TFrame")
        row.pack(fill="x")
        left = ttk.Frame(row, style="Card.TFrame")
        right = ttk.Frame(row, style="Card.TFrame")
        left.pack(side="left", fill="x", expand=True, padx=(0, 6))
        right.pack(side="left", fill="x", expand=True, padx=(6, 0))
        return left, right

    def _money_line(self, parent, caption, value):
        box = ttk.Frame(parent, style="Card.TFrame")
        box.pack(fill="x", pady=2)
        ttk.Label(box, text=caption, style="CardDim.TLabel").pack(anchor="w")
        ttk.Label(box, text=f"{format_money(value)} ₽", style="Card.TLabel", font=("Segoe UI", 11, "bold")).pack(anchor="w")

    def _form_project(self, prj: dict):
        card = self._card(self.tab_data.body, "Данные проекта")
        name = tk.StringVar(value=prj.get("name") or "")
        code = tk.StringVar(value=prj.get("code") or "")
        notes = tk.StringVar(value=prj.get("notes") or "")
        self._bind_str(name, prj, "name", refresh_tree=True)
        self._bind_str(code, prj, "code", refresh_tree=True)
        self._bind_str(notes, prj, "notes")
        self._field(card, "Название проекта", name)
        self._field(card, "Номер / шифр проекта", code)

        money = self._card(self.tab_data.body, "Стоимость")
        pair = self._grid_pair(money)
        self._money_line(pair[0], "Состав, ₽  (детали / закупка)", project_material_cost(prj))
        self._money_line(pair[1], "Работы, ₽", project_labor_cost(prj))
        self._money_line(money, "Итого, ₽  (состав + работы)", project_total_cost(prj))

        notes_card = self._card(self.tab_data.body, "Описание / примечания")
        self._field(notes_card, "Примечания", notes)
        if prj.get("cadSource"):
            cad_card = self._card(self.tab_data.body, "Связь с CAD")
            ttk.Label(cad_card, text=f"Источник: {prj.get('cadSource')}", style="Card.TLabel", wraplength=640).pack(anchor="w")
            ttk.Button(cad_card, text="Связь с CAD-системами…", command=self.open_cad_hub).pack(anchor="w", pady=(8, 0))

        own = checklist_stats(prj.get("checklist") or [])
        all_s = walk_checklists(prj, "assembly")
        stats_card = self._card(self.tab_data.body, "Статус проверки")
        ttk.Label(stats_card, text=self._stats_text("Этот уровень", own), style="Card.TLabel").pack(anchor="w")
        ttk.Label(stats_card, text=self._stats_text("Весь проект", all_s), style="Card.TLabel").pack(anchor="w", pady=(4, 0))

    def _form_assembly(self, asm: dict):
        card = self._card(self.tab_data.body, "Данные сборки")
        name = tk.StringVar(value=asm.get("name") or "")
        des = tk.StringVar(value=asm.get("designation") or "")
        ptype = tk.StringVar(value=asm.get("productType") or "Сборочная единица")
        qty = tk.StringVar(value=str(asm.get("qty") if asm.get("qty") is not None else 1))
        cost = tk.StringVar(value=str(asm.get("cost") if asm.get("cost") is not None else 0))
        notes = tk.StringVar(value=asm.get("notes") or "")
        self._bind_str(name, asm, "name", refresh_tree=True)
        self._bind_str(des, asm, "designation", refresh_tree=True)
        self._bind_str(ptype, asm, "productType")
        self._bind_num(qty, asm, "qty", as_int=True, min_value=1)
        self._bind_num(cost, asm, "cost", min_value=0)
        self._bind_str(notes, asm, "notes")
        split = ttk.Frame(card, style="Card.TFrame")
        split.pack(fill="x")
        prev = ttk.Frame(split, style="Card.TFrame")
        prev.pack(side="left", padx=(0, 14), anchor="n")
        self._preview_column(prev, asm, "assembly")
        fields = ttk.Frame(split, style="Card.TFrame")
        fields.pack(side="left", fill="x", expand=True)
        self._field(fields, "Наименование сборки", name)
        self._field(fields, "Обозначение", des)
        left, right = self._grid_pair(fields)
        self._combo(left, "Тип изделия", ptype, product_types(self.doc))
        self._field(right, "Кол-во в родительской сборке", qty)
        ttk.Button(fields, text="Создать деталь в CAD…", command=self.create_part_in_cad).pack(anchor="w", pady=(12, 4))
        ttk.Button(fields, text="В корзину покупнины", command=self.add_selected_to_cart).pack(anchor="w", pady=(4, 0))

        money = self._card(self.tab_data.body, "Стоимость")
        pair = self._grid_pair(money)
        self._money_line(pair[0], "Состав (детали), ₽", node_material_cost(asm, "assembly"))
        self._money_line(pair[1], "Работы, ₽", node_labor_cost(asm, "assembly"))
        self._money_line(money, "Итого, ₽", node_unit_cost(asm, "assembly"))
        self._field(money, "Стоимость вручную, ₽ (если тип не «сборочная единица»)", cost)

        notes_card = self._card(self.tab_data.body, "Примечания")
        self._field(notes_card, "Примечания", notes)
        build_cad_card(self, self.tab_data.body, asm)
        self._workers_card(asm)
        own = checklist_stats(asm.get("checklist") or [])
        all_s = walk_checklists(asm, "assembly")
        stats_card = self._card(self.tab_data.body, "Статус проверки")
        ttk.Label(stats_card, text=self._stats_text("Этот уровень", own), style="Card.TLabel").pack(anchor="w")
        ttk.Label(stats_card, text=self._stats_text("Вся сборка", all_s), style="Card.TLabel").pack(anchor="w", pady=(4, 0))

    def _form_part(self, part: dict):
        card = self._card(self.tab_data.body, "Данные детали")
        name = tk.StringVar(value=part.get("name") or "")
        des = tk.StringVar(value=part.get("designation") or "")
        ptype = tk.StringVar(value=part.get("productType") or "Деталь")
        material = tk.StringVar(value=part.get("material") or "")
        coating = tk.StringVar(value=part.get("coating") or "")
        revision = tk.StringVar(value=part.get("revision") or "")
        drawn = tk.StringVar(value=part.get("drawnBy") or "")
        checked = tk.StringVar(value=part.get("checkedBy") or "")
        date = tk.StringVar(value=part.get("date") or "")
        qty = tk.StringVar(value=str(part.get("qty") if part.get("qty") is not None else 1))
        cost = tk.StringVar(value=str(part.get("cost") if part.get("cost") is not None else 0))
        notes = tk.StringVar(value=part.get("notes") or "")
        self._bind_str(name, part, "name", refresh_tree=True)
        self._bind_str(des, part, "designation", refresh_tree=True)
        self._bind_str(ptype, part, "productType")
        self._bind_str(material, part, "material")
        self._bind_str(coating, part, "coating")
        self._bind_str(revision, part, "revision")
        self._bind_str(drawn, part, "drawnBy")
        self._bind_str(checked, part, "checkedBy")
        self._bind_str(date, part, "date")
        self._bind_num(qty, part, "qty", as_int=True, min_value=1)
        self._bind_num(cost, part, "cost", min_value=0)
        self._bind_str(notes, part, "notes")
        split = ttk.Frame(card, style="Card.TFrame")
        split.pack(fill="x")
        prev = ttk.Frame(split, style="Card.TFrame")
        prev.pack(side="left", padx=(0, 14), anchor="n")
        self._preview_column(prev, part, "part")
        fields = ttk.Frame(split, style="Card.TFrame")
        fields.pack(side="left", fill="x", expand=True)
        self._field(fields, "Наименование", name)
        self._field(fields, "Обозначение", des)
        left, right = self._grid_pair(fields)
        self._combo(left, "Тип изделия", ptype, product_types(self.doc))
        mats = materials_from_library(self.doc)
        if part.get("material") and part["material"] not in mats:
            mats = mats + [part["material"]]
        self._combo(right, "Материал", material, mats)
        left, right = self._grid_pair(fields)
        self._field(left, "Покрытие", coating)
        self._field(right, "Ревизия", revision)
        left, right = self._grid_pair(fields)
        self._field(left, "Разработал", drawn)
        self._field(right, "Проверил", checked)
        left, right = self._grid_pair(fields)
        self._field(left, "Дата", date)
        self._field(right, "Кол-во в сборке", qty)
        left, right = self._grid_pair(fields)
        self._field(left, "Стоимость детали, ₽ (за 1 шт.)", cost)
        self._money_line(right, "Работы по детали, ₽", workers_pay_sum(part))
        self._field(fields, "Примечания", notes)
        ttk.Button(fields, text="Создать ещё деталь в CAD…", command=self.create_part_in_cad).pack(anchor="w", pady=(12, 4))
        ttk.Button(fields, text="В корзину покупнины", command=self.add_selected_to_cart).pack(anchor="w", pady=(4, 0))
        build_cad_card(self, self.tab_data.body, part)
        self._workers_card(part)
        own = checklist_stats(part.get("checklist") or [])
        stats_card = self._card(self.tab_data.body, "Статус проверки детали")
        ttk.Label(stats_card, text=self._stats_text("Чек-лист", own), style="Card.TLabel").pack(anchor="w")

    def _workers_card(self, node: dict):
        card = self._card(self.tab_data.body, "Работники")
        node.setdefault("workers", [new_worker()])
        cols = ("name", "role", "nick", "pay", "time")
        table = ttk.Treeview(card, columns=cols, show="headings", height=4)
        for c, h, w in (
            ("name", "ФИО", 160),
            ("role", "Роль", 120),
            ("nick", "Ник", 90),
            ("pay", "Оплата, ₽", 90),
            ("time", "Время", 80),
        ):
            table.heading(c, text=h)
            table.column(c, width=w, stretch=c == "name")
        table.pack(fill="x")
        for w in node["workers"]:
            table.insert("", "end", iid=w["id"], values=(
                w.get("name") or "",
                w.get("role") or "",
                w.get("nick") or "",
                w.get("pay") or 0,
                w.get("time") or "",
            ))

        def add():
            w = new_worker()
            node["workers"].append(w)
            self.mark_dirty()
            self.show_selection()

        def edit():
            sel = table.selection()
            if not sel:
                return
            wid = sel[0]
            worker = next((x for x in node["workers"] if x["id"] == wid), None)
            if not worker:
                return
            self._edit_worker(worker)

        def remove():
            sel = table.selection()
            if not sel:
                return
            wid = sel[0]
            node["workers"] = [w for w in node["workers"] if w["id"] != wid]
            if not node["workers"]:
                node["workers"] = [new_worker()]
            self.mark_dirty()
            self.show_selection()

        btns = ttk.Frame(card, style="Card.TFrame")
        btns.pack(fill="x", pady=(6, 0))
        ttk.Button(btns, text="Добавить", command=add).pack(side="left", padx=(0, 4))
        ttk.Button(btns, text="Изменить", command=edit).pack(side="left", padx=4)
        ttk.Button(btns, text="Удалить", command=remove).pack(side="left", padx=4)
        table.bind("<Double-1>", lambda _e: edit())

    def _edit_worker(self, worker: dict):
        win = tk.Toplevel(self.root)
        win.title("Работник")
        win.configure(bg=PM_BG)
        win.transient(self.root)
        win.grab_set()
        win.geometry("380x340")
        panel_header(win, "Работник", PM_HDR, "PropertyManager")
        frm = ttk.Frame(win, style="PM.TFrame")
        frm.pack(fill="both", expand=True, padx=14, pady=12)
        vars_map = {}
        for key, label in (("name", "ФИО"), ("role", "Роль"), ("nick", "Ник"), ("pay", "Оплата, ₽"), ("time", "Время")):
            var = tk.StringVar(value=str(worker.get(key) or ""))
            vars_map[key] = var
            ttk.Label(frm, text=label, style="Dim.TLabel").pack(anchor="w")
            ttk.Entry(frm, textvariable=var).pack(fill="x", pady=(0, 8))

        def ok():
            worker["name"] = vars_map["name"].get()
            worker["role"] = vars_map["role"].get()
            worker["nick"] = vars_map["nick"].get()
            worker["time"] = vars_map["time"].get()
            try:
                worker["pay"] = max(0.0, float(vars_map["pay"].get().replace(",", ".") or 0))
            except ValueError:
                worker["pay"] = 0
            self.mark_dirty()
            win.destroy()
            self.show_selection()

        ttk.Button(frm, text="Сохранить", command=ok, style="Accent.TButton").pack(anchor="e")

    def _stats_text(self, title, stats: dict) -> str:
        t = stats.get("total") or 0
        if not t:
            return f"{title}: нет пунктов"
        return (
            f"{title}: {stats.get('pass', 0)} ок · {stats.get('fail', 0)} замечаний · "
            f"{stats.get('na', 0)} н/д · {stats.get('pending', 0)} не проверено  (всего {t})"
        )

    # ------------------------------------------------------------------ checklist
    def _fill_checklist(self, node):
        self.check_tree.delete(*self.check_tree.get_children())
        if not node:
            self.check_summary.configure(text="")
            return
        stats = checklist_stats(node.get("checklist") or [])
        self.check_summary.configure(text=self._stats_text("Чек-лист", stats))
        for cat in node.get("checklist") or []:
            cid = cat["id"]
            items = cat.get("items") or []
            done = sum(1 for it in items if it.get("status") not in (None, "pending"))
            self.check_tree.insert(
                "",
                "end",
                iid=cid,
                text=f"{cat.get('title') or 'Категория'}   ({done}/{len(items)})",
                values=("", ""),
                tags=("cat",),
                open=True,
            )
            for it in items:
                st = it.get("status") or "pending"
                mark = STATUS_MARKS.get(st, "?")
                label = STATUS_LABELS.get(st, st)
                self.check_tree.insert(
                    cid,
                    "end",
                    iid=it["id"],
                    text=it.get("text") or "",
                    values=(f"{mark}  {label}", it.get("comment") or ""),
                    tags=(st,),
                )

    def _checklist_owner(self):
        _kind, node = self.current_node()
        return node

    def _find_check_item(self, item_id: str):
        node = self._checklist_owner()
        if not node:
            return None, None
        for cat in node.get("checklist") or []:
            for it in cat.get("items") or []:
                if it.get("id") == item_id:
                    return cat, it
        return None, None

    def on_check_click(self, event):
        if self.check_tree.identify_region(event.x, event.y) != "cell":
            return
        col = self.check_tree.identify_column(event.x)
        row = self.check_tree.identify_row(event.y)
        if col == "#1" and row:
            self._cycle_status(row)

    def on_check_double(self, event):
        row = self.check_tree.identify_row(event.y)
        if not row:
            return
        region = self.check_tree.identify_region(event.x, event.y)
        col = self.check_tree.identify_column(event.x)
        if region == "tree":
            self._edit_check_text(row)
        elif col == "#2":
            self._edit_check_comment(row)
        elif col == "#1":
            self._cycle_status(row)

    def _cycle_status(self, item_id: str):
        _cat, it = self._find_check_item(item_id)
        if not it:
            return
        it["status"] = next_status(it.get("status") or "pending")
        self.mark_dirty()
        self._fill_checklist(self._checklist_owner())

    def _edit_check_text(self, item_id: str):
        node = self._checklist_owner()
        if not node:
            return
        for cat in node.get("checklist") or []:
            if cat.get("id") == item_id:
                value = simpledialog.askstring("Категория", "Название категории:", initialvalue=cat.get("title") or "", parent=self.root)
                if value is not None:
                    cat["title"] = value
                    self.mark_dirty()
                    self._fill_checklist(node)
                return
        _cat, it = self._find_check_item(item_id)
        if not it:
            return
        value = simpledialog.askstring("Пункт", "Текст пункта:", initialvalue=it.get("text") or "", parent=self.root)
        if value is not None:
            it["text"] = value
            self.mark_dirty()
            self._fill_checklist(node)

    def _edit_check_comment(self, item_id: str):
        _cat, it = self._find_check_item(item_id)
        if not it:
            return
        value = simpledialog.askstring("Комментарий", "Комментарий / замечание:", initialvalue=it.get("comment") or "", parent=self.root)
        if value is not None:
            it["comment"] = value
            self.mark_dirty()
            self._fill_checklist(self._checklist_owner())

    def add_check_category(self):
        node = self._checklist_owner()
        if not node:
            return
        title = simpledialog.askstring("Категория", "Название новой категории:", parent=self.root)
        if not title:
            return
        node.setdefault("checklist", []).append(new_category(title, []))
        self.mark_dirty()
        self._fill_checklist(node)

    def add_check_item(self):
        node = self._checklist_owner()
        if not node:
            return
        cats = node.get("checklist") or []
        if not cats:
            self.add_check_category()
            return
        sel = self.check_tree.selection()
        cat = None
        if sel:
            cid = sel[0]
            cat = next((c for c in cats if c["id"] == cid), None)
            if not cat:
                parent = self.check_tree.parent(cid)
                cat = next((c for c in cats if c["id"] == parent), None)
        if not cat:
            cat = cats[-1]
        text = simpledialog.askstring("Пункт", "Текст нового пункта:", parent=self.root)
        if not text:
            return
        cat.setdefault("items", []).append(new_item(text))
        self.mark_dirty()
        self._fill_checklist(node)

    def reset_checklist(self):
        node = self._checklist_owner()
        if not node:
            return
        if not messagebox.askyesno(__app_name__, "Сбросить статусы чек-листа на «не проверено»?"):
            return
        for cat in node.get("checklist") or []:
            for it in cat.get("items") or []:
                it["status"] = "pending"
        self.mark_dirty()
        self._fill_checklist(node)

    def clear_checklist(self):
        node = self._checklist_owner()
        if not node:
            messagebox.showinfo(__app_name__, "Сначала выберите проект, сборку или деталь.")
            return
        if not messagebox.askyesno(__app_name__, "Убрать весь чек-лист у этого узла?"):
            return
        from .login import ask_password

        user = (self.user or {}).get("username") or ""
        if not user or not ask_password(self.root, user, "Удаление чек-листа"):
            return
        node["checklist"] = []
        self.mark_dirty()
        self._fill_checklist(node)

    def custom_checklist(self):
        node = self._checklist_owner()
        if not node:
            messagebox.showinfo(__app_name__, "Сначала выберите проект, сборку или деталь.")
            return
        win = tk.Toplevel(self.root)
        win.title("Свой чек-лист")
        win.configure(bg=PM_BG)
        win.transient(self.root)
        win.geometry("640x480")
        win.grab_set()
        panel_header(win, "Свой чек-лист", PM_HDR, "категории и пункты")
        frm = ttk.Frame(win, style="PM.TFrame")
        frm.pack(fill="both", expand=True, padx=12, pady=10)
        ttk.Label(
            frm,
            text="Категория — строка с двоеточием в конце или с # в начале.\n"
            "Пункты — по одному на строку, можно с «- » в начале.",
            style="Dim.TLabel",
            justify="left",
        ).pack(anchor="w", pady=(0, 8))
        text = tk.Text(frm, font=("Segoe UI", 10), wrap="word", height=16, bg="#FFFEF6", fg=TEXT, relief="solid", bd=1)
        text.pack(fill="both", expand=True)
        sample = (
            "Мой чек-лист:\n"
            "- Проверить обозначение\n"
            "- Проверить материал\n"
            "- Проверить комплектность\n"
        )
        text.insert("1.0", sample)
        replace_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            frm,
            text="Заменить текущий чек-лист (иначе добавить к нему)",
            variable=replace_var,
        ).pack(anchor="w", pady=8)

        def apply():
            raw = text.get("1.0", "end")
            cats = _parse_custom_checklist(raw)
            if not cats:
                messagebox.showinfo(__app_name__, "Нет пунктов. Добавьте хотя бы одну строку.", parent=win)
                return
            if replace_var.get():
                from .login import ask_password

                user = (self.user or {}).get("username") or ""
                if not user or not ask_password(self.root, user, "Замена чек-листа"):
                    return
                node["checklist"] = cats
            else:
                node.setdefault("checklist", []).extend(cats)
            self.mark_dirty()
            self._fill_checklist(node)
            win.destroy()

        btns = ttk.Frame(frm, style="PM.TFrame")
        btns.pack(fill="x")
        ttk.Button(btns, text="Сохранить", command=apply, style="Accent.TButton").pack(side="right")
        ttk.Button(btns, text="Отмена", command=win.destroy).pack(side="right", padx=6)

    # ------------------------------------------------------------------ BOM
    def _fill_bom(self, kind, node):
        self.bom_tree.delete(*self.bom_tree.get_children())
        if not node:
            return
        children = []
        if kind == "project":
            for a in node.get("assemblies") or []:
                children.append(("Сборка", a))
        elif kind == "assembly":
            for a in node.get("assemblies") or []:
                children.append(("Сборка", a))
            for p in node.get("parts") or []:
                children.append(("Деталь", p))
        for label, child in children:
            cost = node_unit_cost(child, "assembly" if label == "Сборка" else "part")
            self.bom_tree.insert("", "end", iid=child["id"], values=(
                label,
                child.get("name") or "",
                child.get("designation") or child.get("code") or "",
                child.get("productType") or "",
                child.get("qty") if child.get("qty") is not None else 1,
                format_money(cost),
            ))

    def on_bom_open(self, _event=None):
        sel = self.bom_tree.selection()
        if not sel:
            return
        iid = sel[0]
        if self.tree.exists(iid):
            self.tree.selection_set(iid)
            self.tree.see(iid)
            self.on_tree_select()
            self.tabs.select(self.tab_data)

    # ------------------------------------------------------------------ library
    def open_library(self):
        if self._lib_win and self._lib_win.winfo_exists():
            self._lib_win.lift()
            return
        win = tk.Toplevel(self.root)
        win.title("Библиотека")
        win.configure(bg=WORK)
        win.geometry("640x480")
        win.transient(self.root)
        self._lib_win = win
        panel_header(win, "Библиотека", FM_HDR, "Design Library")
        nb = ttk.Notebook(win)
        nb.pack(fill="both", expand=True, padx=6, pady=6)
        mats = ttk.Frame(nb, style="PM.TFrame")
        types = ttk.Frame(nb, style="PM.TFrame")
        nb.add(mats, text="Материалы")
        nb.add(types, text="Типы изделий")
        self._list_editor(mats, "materials", "Материал")
        self._list_editor(types, "productTypes", "Тип изделия", defaults_ok=True)

    def _list_editor(self, parent, lib_key: str, item_name: str, defaults_ok=False):
        lib = self.doc.setdefault("library", {})
        values = lib.setdefault(lib_key, [])

        def as_text(item):
            if isinstance(item, str):
                return item
            return str((item or {}).get("name") or "")

        lst = tk.Listbox(
            parent,
            font=("Segoe UI", 10),
            bg=FM_BG,
            fg=TEXT,
            selectbackground=FM_SEL,
            selectforeground=FM_SEL_FG,
            relief="flat",
            highlightthickness=1,
            highlightbackground="#8A929A",
            activestyle="none",
        )
        lst.pack(fill="both", expand=True, padx=8, pady=8)

        def reload():
            lst.delete(0, "end")
            for item in values:
                text = as_text(item)
                if text:
                    lst.insert("end", text)

        def add():
            value = simpledialog.askstring("Библиотека", f"Новый {item_name.lower()}:", parent=self._lib_win)
            if not value or not value.strip():
                return
            value = value.strip()
            existing = {as_text(x).casefold() for x in values}
            if value.casefold() in existing:
                return
            values.append(value)
            self.mark_dirty()
            reload()

        def remove():
            sel = lst.curselection()
            if not sel:
                return
            name = lst.get(sel[0])
            keep = []
            for item in values:
                if as_text(item) != name:
                    keep.append(item)
            values[:] = keep
            self.mark_dirty()
            reload()

        btns = ttk.Frame(parent, style="PM.TFrame")
        btns.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(btns, text="Добавить", command=add).pack(side="left", padx=(0, 4))
        ttk.Button(btns, text="Удалить", command=remove).pack(side="left")
        reload()
