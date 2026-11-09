"""Цвета и виджеты в духе SolidWorks: Command Manager, FeatureManager, PropertyManager."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

# Хром окна и шапка
NAVY = "#163A5F"
NAVY_DEEP = "#0F2740"
NAVY_MID = "#2C5282"

# Акцент SolidWorks
SW_BLUE = "#0066A1"
SW_BLUE_HI = "#1A7FBF"
SW_BLUE_SOFT = "#C5DFF0"
SW_ORANGE = "#E87722"
SW_RED = "#C8102E"

# Command Manager
CMD_BG = "#E4E7EB"
CMD_BTN = "#F3F4F6"
CMD_BTN_HOVER = "#FFFFFF"
CMD_BTN_ACTIVE = "#D7E8F5"
CMD_LINE = "#B7BDC4"
CMD_TEXT = "#2A3138"

# Рабочая область вокруг панелей
WORK = "#B8BFC6"

# FeatureManager
FM_HDR = "#3D5A80"
FM_BG = "#FFFFFF"
FM_SEL = "#C5DFF0"
FM_SEL_FG = "#0F2740"

# PropertyManager — фирменный кремовый
PM_BG = "#F3EDC8"
PM_GROUP = "#F7F3D6"
PM_HDR = "#2F5F8F"
PM_BORDER = "#C4B57A"
PM_GROUP_HDR = "#5A7DA6"

# Текст и статусы
TEXT = "#1F2A33"
DIM = "#5C6770"
OK = "#2E7D32"
DANGER = "#C62828"
STATUS_BG = "#D5D9DE"
ENTRY_BG = "#FFFFFF"


def apply_style(root: tk.Tk) -> ttk.Style:
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    font = ("Segoe UI", 9)
    font_ui = ("Segoe UI", 10)

    style.configure(".", font=font_ui, background=WORK, foreground=TEXT)
    style.configure("TFrame", background=WORK)
    style.configure("Main.TFrame", background=PM_BG)
    style.configure("Card.TFrame", background=PM_GROUP)
    style.configure("PM.TFrame", background=PM_BG)
    style.configure("FM.TFrame", background=FM_BG)
    style.configure("Cmd.TFrame", background=CMD_BG)
    style.configure("Work.TFrame", background=WORK)

    style.configure("TLabel", background=WORK, foreground=TEXT, font=font_ui)
    style.configure("Dim.TLabel", background=PM_BG, foreground=DIM, font=("Segoe UI", 9))
    style.configure("Card.TLabel", background=PM_GROUP, foreground=TEXT, font=font_ui)
    style.configure("CardDim.TLabel", background=PM_GROUP, foreground=DIM, font=("Segoe UI", 8))
    style.configure("H2.TLabel", background=PM_GROUP_HDR, foreground="#FFFFFF", font=("Segoe UI", 9, "bold"))
    style.configure("PMTitle.TLabel", background=PM_HDR, foreground="#FFFFFF", font=("Segoe UI", 10, "bold"))
    style.configure("PMSub.TLabel", background=PM_HDR, foreground="#D6E7F5", font=("Segoe UI", 8))
    style.configure("FMTitle.TLabel", background=FM_HDR, foreground="#FFFFFF", font=("Segoe UI", 9, "bold"))
    style.configure("GroupCap.TLabel", background=CMD_BG, foreground=DIM, font=("Segoe UI", 8))
    style.configure("Status.TLabel", background=STATUS_BG, foreground=TEXT, font=("Segoe UI", 8))
    style.configure("Status.TFrame", background=STATUS_BG)
    style.configure("Ready.TLabel", background=STATUS_BG, foreground=OK, font=("Segoe UI", 8, "bold"))

    style.configure(
        "TButton",
        background=CMD_BTN,
        foreground=CMD_TEXT,
        bordercolor=CMD_LINE,
        lightcolor=CMD_BTN,
        darkcolor=CMD_LINE,
        padding=(10, 5),
        font=font,
        relief="flat",
    )
    style.map(
        "TButton",
        background=[("active", CMD_BTN_HOVER), ("pressed", CMD_BTN_ACTIVE)],
        bordercolor=[("active", SW_BLUE)],
    )
    style.configure(
        "Accent.TButton",
        background=SW_BLUE,
        foreground="#FFFFFF",
        bordercolor=NAVY_MID,
        lightcolor=SW_BLUE_HI,
        darkcolor=NAVY,
        padding=(10, 5),
        font=("Segoe UI", 9, "bold"),
    )
    style.map("Accent.TButton", background=[("active", SW_BLUE_HI), ("pressed", NAVY_MID)])

    style.configure(
        "TEntry",
        fieldbackground=ENTRY_BG,
        foreground=TEXT,
        bordercolor=CMD_LINE,
        lightcolor=ENTRY_BG,
        darkcolor=CMD_LINE,
        padding=4,
        insertcolor=TEXT,
    )
    style.map("TEntry", bordercolor=[("focus", SW_BLUE)])
    style.configure(
        "TCombobox",
        fieldbackground=ENTRY_BG,
        background=CMD_BTN,
        foreground=TEXT,
        bordercolor=CMD_LINE,
        arrowcolor=NAVY,
        padding=3,
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", ENTRY_BG)],
        bordercolor=[("focus", SW_BLUE)],
    )

    style.configure("TNotebook", background=PM_BG, borderwidth=0, tabmargins=(4, 4, 4, 0))
    style.configure(
        "TNotebook.Tab",
        background="#E6E0B8",
        foreground=TEXT,
        padding=(14, 6),
        font=("Segoe UI", 9),
        bordercolor=PM_BORDER,
        lightcolor="#E6E0B8",
        darkcolor=PM_BORDER,
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", PM_BG), ("active", "#F8F3D4")],
        foreground=[("selected", NAVY)],
        font=[("selected", ("Segoe UI", 9, "bold"))],
    )

    style.configure(
        "Treeview",
        background=FM_BG,
        fieldbackground=FM_BG,
        foreground=TEXT,
        rowheight=22,
        font=("Segoe UI", 9),
        bordercolor=CMD_LINE,
        lightcolor=FM_BG,
        darkcolor=CMD_LINE,
    )
    style.configure(
        "Treeview.Heading",
        background="#EEF1F4",
        foreground=NAVY,
        font=("Segoe UI", 8, "bold"),
        bordercolor=CMD_LINE,
        relief="flat",
    )
    style.map(
        "Treeview",
        background=[("selected", FM_SEL)],
        foreground=[("selected", FM_SEL_FG)],
    )
    style.map("Treeview.Heading", background=[("active", SW_BLUE_SOFT)])

    style.configure("TScrollbar", background=CMD_BG, troughcolor="#D8DCE0", bordercolor=CMD_LINE, arrowcolor=NAVY)
    style.configure("TPanedwindow", background=WORK)
    style.configure("Sash", sashthickness=6, background=WORK)
    style.configure("TSeparator", background=CMD_LINE)
    style.configure("TLabelframe", background=PM_GROUP, bordercolor=PM_BORDER)
    style.configure("TLabelframe.Label", background=PM_GROUP, foreground=SW_BLUE, font=("Segoe UI", 8, "bold"))
    return style


class CommandButton(tk.Frame):
    """Кнопка Command Manager: значок сверху, подпись снизу."""

    def __init__(self, parent, icon: str, label: str, command, width=78):
        super().__init__(parent, bg=CMD_BG, width=width, height=62)
        self.pack_propagate(False)
        self._command = command
        self._bg = CMD_BG
        inner = tk.Frame(self, bg=CMD_BG, highlightthickness=1, highlightbackground=CMD_BG, highlightcolor=SW_BLUE)
        inner.pack(fill="both", expand=True, padx=2, pady=2)
        self._inner = inner
        ic = tk.Label(inner, text=icon, bg=CMD_BG, fg=NAVY, font=("Segoe UI", 14), cursor="hand2")
        ic.pack(pady=(6, 0))
        cap = tk.Label(inner, text=label, bg=CMD_BG, fg=CMD_TEXT, font=("Segoe UI", 8), cursor="hand2")
        cap.pack()
        self._parts = (inner, ic, cap)
        for w in self._parts:
            w.bind("<Enter>", self._on_enter)
            w.bind("<Leave>", self._on_leave)
            w.bind("<Button-1>", self._on_click)

    def _paint(self, bg: str, border: str):
        self._inner.configure(bg=bg, highlightbackground=border)
        for w in self._parts:
            w.configure(bg=bg)

    def _on_enter(self, _e=None):
        self._paint(CMD_BTN_HOVER, SW_BLUE)

    def _on_leave(self, _e=None):
        self._paint(CMD_BG, CMD_BG)

    def _on_click(self, _e=None):
        if self._command:
            self._command()


def command_group(parent, title: str, buttons: list[tuple[str, str, object]]) -> tk.Frame:
    box = tk.Frame(parent, bg=CMD_BG)
    row = tk.Frame(box, bg=CMD_BG)
    row.pack()
    for icon, label, cmd in buttons:
        CommandButton(row, icon, label, cmd).pack(side="left")
    tk.Label(box, text=title, bg=CMD_BG, fg=DIM, font=("Segoe UI", 8)).pack(pady=(0, 4))
    return box


def v_sep(parent, bg=CMD_BG, color=CMD_LINE) -> tk.Frame:
    wrap = tk.Frame(parent, bg=bg, width=9)
    line = tk.Frame(wrap, bg=color, width=1)
    line.place(relx=0.5, y=8, relheight=0.72, anchor="n")
    return wrap


def panel_header(parent, title: str, bg: str, subtitle: str | None = None) -> tuple[tk.Frame, tk.Label, tk.Label | None]:
    bar = tk.Frame(parent, bg=bg, height=28)
    bar.pack(fill="x")
    bar.pack_propagate(False)
    left = tk.Frame(bar, bg=bg)
    left.pack(side="left", fill="y", padx=10)
    title_lbl = tk.Label(left, text=title, bg=bg, fg="#FFFFFF", font=("Segoe UI", 9, "bold"))
    title_lbl.pack(side="left", pady=4)
    sub_lbl = None
    if subtitle is not None:
        sub_lbl = tk.Label(left, text=subtitle, bg=bg, fg="#D6E7F5", font=("Segoe UI", 8))
        sub_lbl.pack(side="left", padx=(10, 0), pady=4)
    tk.Frame(parent, bg=SW_ORANGE, height=2).pack(fill="x")
    return bar, title_lbl, sub_lbl
