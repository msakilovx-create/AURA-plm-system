"""Экран входа и регистрации на главном окне."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from . import __app_name__
from .auth import find_user, load_users, login, register_user, verify_password
from .theme import NAVY, SW_BLUE, SW_RED, TEXT, WORK


def mount_login(root: tk.Tk, on_success) -> None:
    for w in root.winfo_children():
        w.destroy()
    root.title(f"Вход — {__app_name__}")
    root.geometry("460x520")
    root.minsize(420, 480)
    root.configure(bg=WORK)
    root.deiconify()
    root.lift()
    root.focus_force()
    try:
        root.attributes("-topmost", True)
        root.after(400, lambda: root.attributes("-topmost", False))
    except tk.TclError:
        pass

    header = tk.Frame(root, bg=NAVY)
    header.pack(fill="x")
    tk.Label(header, text="AURA PLM System", bg=NAVY, fg="#FFFFFF", font=("Segoe UI", 16, "bold")).pack(pady=(14, 2))
    tk.Label(header, text="Войдите или создайте учётную запись", bg=NAVY, fg="#A9C4DA", font=("Segoe UI", 9)).pack(pady=(0, 12))
    tk.Frame(root, bg="#E87722", height=3).pack(fill="x")

    body = tk.Frame(root, bg=WORK)
    body.pack(fill="both", expand=True, padx=24, pady=18)

    mode = tk.StringVar(value="login" if (load_users().get("users") or []) else "register")
    tabs = tk.Frame(body, bg=WORK)
    tabs.pack(fill="x", pady=(0, 14))

    def paint_tabs():
        for b in (btn_login, btn_reg):
            b.configure(bg="#D9DEE3", fg=TEXT, font=("Segoe UI", 10))
        if mode.get() == "login":
            btn_login.configure(bg=SW_BLUE, fg="#fff", font=("Segoe UI", 10, "bold"))
        else:
            btn_reg.configure(bg=SW_BLUE, fg="#fff", font=("Segoe UI", 10, "bold"))
        if mode.get() == "register":
            pw2_box.pack(fill="x", pady=(0, 8), after=pw_box)
            go.configure(text="Создать учётную запись")
        else:
            pw2_box.pack_forget()
            go.configure(text="Войти")

    def set_mode(m):
        mode.set(m)
        paint_tabs()

    btn_login = tk.Button(tabs, text="Войти", relief="flat", cursor="hand2", command=lambda: set_mode("login"))
    btn_reg = tk.Button(tabs, text="Регистрация", relief="flat", cursor="hand2", command=lambda: set_mode("register"))
    btn_login.pack(side="left", expand=True, fill="x", ipady=8, padx=(0, 4))
    btn_reg.pack(side="left", expand=True, fill="x", ipady=8, padx=(4, 0))

    user_var = tk.StringVar()
    pw_var = tk.StringVar()
    pw2_var = tk.StringVar()

    tk.Label(body, text="Логин", bg=WORK, fg="#5C6770", font=("Segoe UI", 9)).pack(anchor="w")
    ttk.Entry(body, textvariable=user_var, font=("Segoe UI", 11)).pack(fill="x", pady=(2, 10), ipady=4)

    pw_box = tk.Frame(body, bg=WORK)
    pw_box.pack(fill="x", pady=(0, 8))
    tk.Label(pw_box, text="Пароль", bg=WORK, fg="#5C6770", font=("Segoe UI", 9)).pack(anchor="w")
    ttk.Entry(pw_box, textvariable=pw_var, show="•", font=("Segoe UI", 11)).pack(fill="x", pady=(2, 0), ipady=4)

    pw2_box = tk.Frame(body, bg=WORK)
    tk.Label(pw2_box, text="Пароль ещё раз", bg=WORK, fg="#5C6770", font=("Segoe UI", 9)).pack(anchor="w")
    ttk.Entry(pw2_box, textvariable=pw2_var, show="•", font=("Segoe UI", 11)).pack(fill="x", pady=(2, 0), ipady=4)

    hint = tk.Label(
        body,
        text="Первый зарегистрированный пользователь становится администратором PLM.",
        bg=WORK, fg="#5C6770", font=("Segoe UI", 8), wraplength=400, justify="left",
    )
    hint.pack(anchor="w", pady=(8, 12))

    def submit(_e=None):
        name = user_var.get().strip()
        pw = pw_var.get()
        try:
            if mode.get() == "register":
                if pw != pw2_var.get():
                    raise ValueError("Пароли не совпадают.")
                register_user(name, pw)
                rec, key = login(name, pw)
            else:
                rec, key = login(name, pw)
        except Exception as exc:
            messagebox.showerror(__app_name__, str(exc), parent=root)
            return
        on_success({"user": rec, "key": key, "username": rec["username"]})

    go = tk.Button(
        body, text="Войти", command=submit, bg=SW_RED, fg="#fff",
        relief="flat", font=("Segoe UI", 11, "bold"), cursor="hand2",
        activebackground="#A50D24", activeforeground="#fff",
    )
    go.pack(fill="x", ipady=10, pady=(4, 0))
    root.bind("<Return>", submit)
    paint_tabs()


def ask_password(parent, username: str, title: str = "Подтверждение паролем") -> bool:
    ok = {"v": False}
    win = tk.Toplevel(parent)
    win.title(title)
    win.configure(bg=WORK)
    win.geometry("380x220")
    win.transient(parent)
    win.grab_set()
    win.resizable(False, False)
    win.lift()
    bar = tk.Frame(win, bg=NAVY)
    bar.pack(fill="x")
    tk.Label(bar, text=title, bg=NAVY, fg="#fff", font=("Segoe UI", 11, "bold")).pack(side="left", padx=12, pady=8)
    tk.Label(bar, text=username, bg=NAVY, fg="#A9C4DA", font=("Segoe UI", 8)).pack(side="right", padx=12)
    frm = tk.Frame(win, bg=WORK)
    frm.pack(fill="both", expand=True, padx=16, pady=12)
    tk.Label(frm, text="Пароль аккаунта", bg=WORK, fg="#5C6770").pack(anchor="w")
    var = tk.StringVar()
    ent = ttk.Entry(frm, textvariable=var, show="•")
    ent.pack(fill="x", pady=(4, 12), ipady=4)
    ent.focus_set()

    def submit(_e=None):
        rec = find_user(username)
        if rec and verify_password(rec, var.get()):
            ok["v"] = True
            win.destroy()
            return
        messagebox.showerror(__app_name__, "Неверный пароль.", parent=win)

    tk.Button(frm, text="Подтвердить", command=submit, bg=SW_BLUE, fg="#fff", relief="flat", cursor="hand2").pack(anchor="e", ipadx=12, ipady=6)
    win.bind("<Return>", submit)
    parent.wait_window(win)
    return ok["v"]
