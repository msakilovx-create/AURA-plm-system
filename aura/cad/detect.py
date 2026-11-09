"""Поиск установленных и запущенных CAD на Windows."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .systems import CAD_SYSTEMS, CadSystem

CREATE_NO_WINDOW = 0x08000000


def _tasklist_names() -> set[str]:
    names: set[str] = set()
    try:
        raw = subprocess.check_output(
            ["tasklist", "/FO", "CSV", "/NH"],
            creationflags=CREATE_NO_WINDOW,
            stderr=subprocess.DEVNULL,
            timeout=8,
        )
    except Exception:
        return names
    text = raw.decode("cp866", errors="ignore") or raw.decode("utf-8", errors="ignore")
    for line in text.splitlines():
        part = line.strip().strip('"')
        if not part:
            continue
        exe = part.split('","')[0].strip('"')
        if exe:
            names.add(exe.lower())
    return names


def _uninstall_display_names() -> list[str]:
    names: list[str] = []
    try:
        import winreg
    except ImportError:
        return names
    roots = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]
    for hive, path in roots:
        try:
            key = winreg.OpenKey(hive, path)
        except OSError:
            continue
        try:
            i = 0
            while True:
                try:
                    sub = winreg.EnumKey(key, i)
                except OSError:
                    break
                i += 1
                try:
                    sk = winreg.OpenKey(key, sub)
                except OSError:
                    continue
                try:
                    name, _ = winreg.QueryValueEx(sk, "DisplayName")
                    if name:
                        names.append(str(name))
                except OSError:
                    pass
                finally:
                    winreg.CloseKey(sk)
        finally:
            winreg.CloseKey(key)
    return names


def _software_keys() -> list[str]:
    keys: list[str] = []
    try:
        import winreg
    except ImportError:
        return keys
    for hive, path in (
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE"),
    ):
        try:
            key = winreg.OpenKey(hive, path)
        except OSError:
            continue
        try:
            i = 0
            while True:
                try:
                    keys.append(winreg.EnumKey(key, i))
                except OSError:
                    break
                i += 1
        finally:
            winreg.CloseKey(key)
    return keys


def _looks_installed(sys: CadSystem, uninstall: list[str], sw_keys: list[str], path_hit: bool) -> bool:
    if path_hit:
        return True
    blob = " | ".join(uninstall + sw_keys).lower()
    return any(hint.lower() in blob for hint in sys.registry_hints)


def _path_hit(sys: CadSystem) -> str:
    search_dirs = []
    for env in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432"):
        root = os.environ.get(env)
        if root:
            search_dirs.append(Path(root))
    needles = {
        "solidworks": ("SOLIDWORKS", "SolidWorks"),
        "kompas": ("ASCON", "KOMPAS"),
        "inventor": ("Autodesk", "Inventor"),
        "solidedge": ("Solid Edge", "SolidEdge"),
        "creo": ("PTC", "Creo"),
        "nx": ("Siemens", "NX"),
        "catia": ("Dassault Systemes", "CATIA"),
        "tflex": ("T-FLEX", "Top Systems"),
        "freecad": ("FreeCAD",),
        "autocad": ("Autodesk", "AutoCAD"),
        "nanocad": ("Nanosoft", "nanoCAD"),
    }
    for folder in needles.get(sys.id, ()):
        for root in search_dirs:
            candidate = root / folder
            if candidate.exists():
                return str(candidate)
    return ""


def detect_cad_systems() -> list[dict]:
    running = _tasklist_names()
    uninstall = _uninstall_display_names()
    sw_keys = _software_keys()
    result = []
    for sys in CAD_SYSTEMS:
        if sys.id == "step":
            result.append(
                {
                    "id": sys.id,
                    "name": sys.name,
                    "installed": True,
                    "running": False,
                    "path": "",
                    "slot": sys.slot,
                }
            )
            continue
        path = _path_hit(sys)
        is_running = any(proc.lower() in running for proc in sys.processes)
        installed = is_running or _looks_installed(sys, uninstall, sw_keys, bool(path))
        result.append(
            {
                "id": sys.id,
                "name": sys.name,
                "installed": installed,
                "running": is_running,
                "path": path,
                "slot": sys.slot,
            }
        )
    return result


def authoring_cad_systems() -> list[dict]:
    """CAD, в которых можно создать деталь: установлены на этом ПК."""
    skip = {"step", "teamcenter"}
    return [s for s in detect_cad_systems() if s.get("id") not in skip and s.get("installed")]
