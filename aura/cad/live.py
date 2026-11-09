"""Активный документ из запущенной CAD: COM, заголовок окна NX, недавние файлы."""

from __future__ import annotations

import ctypes
import os
import subprocess
from ctypes import wintypes as wt
from pathlib import Path

CREATE_NO_WINDOW = 0x08000000

_SCRIPTS = {
    "solidworks": r"""
try {
  $sw = [Runtime.InteropServices.Marshal]::GetActiveObject('SldWorks.Application')
  $doc = $sw.ActiveDoc
  if ($doc -eq $null) { Write-Output '' } else { Write-Output $doc.GetPathName() }
} catch { Write-Output '' }
""",
    "inventor": r"""
try {
  $app = [Runtime.InteropServices.Marshal]::GetActiveObject('Inventor.Application')
  $doc = $app.ActiveDocument
  if ($doc -eq $null) { Write-Output '' } else { Write-Output $doc.FullFileName }
} catch { Write-Output '' }
""",
    "kompas": r"""
$ids = @('KOMPAS.Application.7','Kompas.Application.5','KOMPAS.Application.7.0')
foreach ($id in $ids) {
  try {
    $k = [Runtime.InteropServices.Marshal]::GetActiveObject($id)
    try { Write-Output $k.ActiveDocument.Path; return } catch {}
    try { Write-Output $k.ActiveDocument.FullFileName; return } catch {}
  } catch {}
}
Write-Output ''
""",
    "autocad": r"""
try {
  $app = [Runtime.InteropServices.Marshal]::GetActiveObject('AutoCAD.Application')
  $doc = $app.ActiveDocument
  if ($doc -eq $null) { Write-Output '' } else { Write-Output $doc.FullName }
} catch { Write-Output '' }
""",
}

_NX_EXTS = (".prt", ".prt.1", ".asm", ".jt", ".step", ".stp")
_CAD_EXTS = {
    "nx": (".prt", ".jt", ".stp", ".step"),
    "solidworks": (".sldasm", ".sldprt", ".slddrw"),
    "kompas": (".a3d", ".m3d", ".cdw"),
    "inventor": (".iam", ".ipt"),
    "solidedge": (".asm", ".par"),
    "catia": (".catproduct", ".catpart"),
    "freecad": (".fcstd",),
    "autocad": (".dwg", ".dxf"),
    "step": (".step", ".stp"),
}


class GrabError(RuntimeError):
    def __init__(self, system_id: str, message: str, managed=False):
        super().__init__(message)
        self.system_id = system_id
        self.managed = managed


def _ps_output(script: str, timeout: int = 12) -> str:
    try:
        raw = subprocess.check_output(
            ["powershell", "-NoProfile", "-STA", "-Command", script],
            creationflags=CREATE_NO_WINDOW,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
        )
    except Exception:
        return ""
    return raw.decode("utf-8", errors="ignore").strip().strip('"')


def _com_path(system_id: str) -> Path | None:
    script = _SCRIPTS.get(system_id)
    if not script:
        return None
    text = _ps_output(script)
    if not text:
        return None
    path = Path(text)
    return path if path.exists() else None


def _running_pids(*exe_names: str) -> dict[int, str]:
    names = {n.lower() for n in exe_names}
    found: dict[int, str] = {}
    try:
        raw = subprocess.check_output(
            ["tasklist", "/FO", "CSV", "/NH"],
            creationflags=CREATE_NO_WINDOW,
            stderr=subprocess.DEVNULL,
            timeout=8,
        )
    except Exception:
        return found
    text = raw.decode("cp866", errors="ignore") or raw.decode("utf-8", errors="ignore")
    for line in text.splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        if not parts:
            continue
        exe = parts[0]
        if exe.lower() not in names:
            continue
        try:
            found[int(parts[1])] = exe
        except (IndexError, ValueError):
            continue
    return found


def _visible_window_titles(pids: set[int] | None = None) -> list[str]:
    user32 = ctypes.windll.user32
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    titles: list[str] = []

    def cb(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        pid = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pids is not None and pid.value not in pids:
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n <= 0:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        title = (buf.value or "").strip()
        if title:
            titles.append(title)
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return titles


def _path_from_title(title: str) -> Path | None:
    text = title.replace("/", "\\")
    lower = text.lower()
    for ext in (".sldasm", ".sldprt", ".prt", ".a3d", ".m3d", ".iam", ".ipt", ".catproduct", ".step", ".stp", ".jt"):
        idx = lower.find(ext)
        if idx < 0:
            continue
        end = idx + len(ext)
        start = 0
        chunk = text[start:end]
        # путь с диска
        for i, ch in enumerate(chunk):
            if ch.isalpha() and i + 1 < len(chunk) and chunk[i + 1] == ":":
                cand = Path(chunk[i:])
                if cand.exists():
                    return cand
        name = Path(chunk).name
        if name.lower().endswith(ext):
            return Path(name)
    return None


def _resolve_lnk(lnk: Path) -> Path | None:
    script = (
        "$s = New-Object -ComObject WScript.Shell; "
        f"$t = $s.CreateShortcut('{str(lnk).replace(chr(39), chr(39)+chr(39))}').TargetPath; "
        "Write-Output $t"
    )
    text = _ps_output(script, timeout=6)
    if not text:
        return None
    path = Path(text)
    return path if path.exists() else None


def recent_files(exts: tuple[str, ...], limit: int = 15) -> list[Path]:
    rec = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Recent"
    if not rec.exists():
        return []
    wanted = tuple(e.lower() for e in exts)
    lnks = sorted(rec.glob("*.lnk"), key=lambda p: p.stat().st_mtime, reverse=True)
    out: list[Path] = []
    seen = set()
    for lnk in lnks[:80]:
        name = lnk.stem.lower()
        if not any(name.endswith(ext.lstrip(".")) or any(name.endswith(ext) for ext in wanted) for ext in wanted):
            # shortcut name often includes extension
            if not any(ext.lstrip(".") in name for ext in wanted):
                continue
        target = _resolve_lnk(lnk)
        if target is None:
            continue
        if target.suffix.lower() not in wanted and not any(str(target).lower().endswith(ext) for ext in wanted):
            continue
        key = str(target.resolve()).lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(target)
        if len(out) >= limit:
            break
    return out


def _nx_path_from_windows() -> Path | None:
    pids = set(_running_pids("ugraf.exe", "ugs_router.exe"))
    if not pids:
        return None
    for title in _visible_window_titles(pids):
        got = _path_from_title(title)
        if got is None:
            continue
        if got.exists():
            return got
        # только имя — ищем среди недавних
        for rec in recent_files(_NX_EXTS):
            if rec.name.lower() == got.name.lower():
                return rec
    return None


def teamcenter_running() -> bool:
    return bool(_running_pids("teamcenter.exe", "portal.exe", "awclient.exe", "tcserver.exe"))


def nx_looks_managed() -> bool:
    """NX открыт, но в заголовке нет файла на диске — типичный режим Teamcenter."""
    pids = set(_running_pids("ugraf.exe"))
    if not pids:
        return False
    titles = _visible_window_titles(pids)
    has_file = any(_path_from_title(t) for t in titles)
    return (not has_file) and (teamcenter_running() or any("teamcenter" in t.lower() or "тc" in t.lower() for t in titles))


def active_document_path(system_id: str) -> Path | None:
    path = _com_path(system_id)
    if path:
        return path
    if system_id == "nx":
        return _nx_path_from_windows()
    return None


def file_filter_for(system_id: str) -> list[tuple[str, str]]:
    mapping = {
        "nx": ("Siemens NX", "*.prt;*.jt;*.stp;*.step"),
        "solidworks": ("SolidWorks", "*.sldasm;*.sldprt;*.slddrw"),
        "kompas": ("КОМПАС-3D", "*.a3d;*.m3d;*.cdw"),
        "inventor": ("Inventor", "*.iam;*.ipt"),
        "teamcenter": ("Teamcenter", "*.plmxml;*.xml;*.bcz;*.csv"),
        "step": ("STEP", "*.step;*.stp"),
    }
    spec = mapping.get(system_id, ("CAD", "*.*"))
    return [spec, ("Все файлы", "*.*")]
