#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Запуск оконного приложения AURA PLM System."""

import sys
import traceback
from pathlib import Path

# Чтобы пакет aura находился рядом со скриптом
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main():
    try:
        from aura.app import AuraApp

        AuraApp().run()
    except Exception:
        try:
            import tkinter as tk
            from tkinter import messagebox

            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("AURA PLM System", "Ошибка запуска:\n\n" + traceback.format_exc())
            root.destroy()
        except Exception:
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
