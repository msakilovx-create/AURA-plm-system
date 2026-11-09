"""Просмотр STL и STEP в окне AURA PLM."""

from __future__ import annotations

import gzip
import hashlib
import math
import struct
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

import tkinter as tk

from .theme import NAVY, TEXT, WORK

_CACHE_DIR = Path(tempfile.gettempdir()) / "aura_plm_mesh"


def load_stl(path: Path) -> list[tuple]:
    data = path.read_bytes()
    if _is_binary_stl(data):
        return _parse_binary_stl(data)
    return _parse_ascii_stl(data.decode("utf-8", errors="ignore"))


def _is_binary_stl(data: bytes) -> bool:
    if len(data) < 84:
        return False
    n = struct.unpack_from("<I", data, 80)[0]
    return 84 + n * 50 == len(data)


def _parse_binary_stl(data: bytes) -> list[tuple]:
    n = struct.unpack_from("<I", data, 80)[0]
    tris = []
    off = 84
    cap = min(n, 80000)
    step = max(1, n // cap) if n > cap else 1
    i = 0
    while i < n:
        nx, ny, nz, x1, y1, z1, x2, y2, z2, x3, y3, z3 = struct.unpack_from("<12f", data, off + i * 50)
        tris.append((x1, y1, z1, x2, y2, z2, x3, y3, z3, nx, ny, nz))
        i += step
    return tris


def _parse_ascii_stl(text: str) -> list[tuple]:
    tris = []
    verts = []
    nx = ny = nz = 0.0
    for line in text.splitlines():
        p = line.strip().split()
        if not p:
            continue
        key = p[0].lower()
        if key == "facet" and len(p) >= 5:
            nx, ny, nz = float(p[2]), float(p[3]), float(p[4])
            verts = []
        elif key == "vertex" and len(p) >= 4:
            verts.append((float(p[1]), float(p[2]), float(p[3])))
        elif key == "endfacet" and len(verts) == 3:
            (x1, y1, z1), (x2, y2, z2), (x3, y3, z3) = verts
            tris.append((x1, y1, z1, x2, y2, z2, x3, y3, z3, nx, ny, nz))
            if len(tris) >= 80000:
                break
    return tris


def _tri(pos, a, b, c):
    x1, y1, z1 = pos[a]
    x2, y2, z2 = pos[b]
    x3, y3, z3 = pos[c]
    ax, ay, az = x2 - x1, y2 - y1, z2 - z1
    bx, by, bz = x3 - x1, y3 - y1, z3 - z1
    nx = ay * bz - az * by
    ny = az * bx - ax * bz
    nz = ax * by - ay * bx
    return (x1, y1, z1, x2, y2, z2, x3, y3, z3, nx, ny, nz)


def tessellate_step(path: Path) -> list[tuple]:
    try:
        import gmsh
    except ImportError as exc:
        raise RuntimeError("Для STEP нужен пакет gmsh: pip install gmsh") from exc

    src = path
    tmp = None
    if path.suffix.lower() == ".stpz":
        tmp = Path(tempfile.mkdtemp()) / (path.stem + ".step")
        tmp.write_bytes(gzip.decompress(path.read_bytes()))
        src = tmp

    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.option.setNumber("General.Verbosity", 0)
        gmsh.open(str(src))
        try:
            xmin, ymin, zmin, xmax, ymax, zmax = gmsh.model.getBoundingBox(-1, -1)
            diag = math.sqrt((xmax - xmin) ** 2 + (ymax - ymin) ** 2 + (zmax - zmin) ** 2) or 1.0
            gmsh.option.setNumber("Mesh.MeshSizeMax", diag / 28.0)
            gmsh.option.setNumber("Mesh.MeshSizeMin", diag / 80.0)
        except Exception:
            pass
        gmsh.model.mesh.generate(2)
        node_tags, coord, _ = gmsh.model.mesh.getNodes()
        pos = {}
        for i, tag in enumerate(node_tags):
            pos[int(tag)] = (float(coord[i * 3]), float(coord[i * 3 + 1]), float(coord[i * 3 + 2]))
        elem_types, _elem_tags, elem_nodes = gmsh.model.mesh.getElements(2)
        tris: list[tuple] = []
        cap = 80000
        for etype, nodes in zip(elem_types, elem_nodes):
            n = [int(x) for x in nodes]
            if int(etype) == 2:
                for i in range(0, len(n) - 2, 3):
                    tris.append(_tri(pos, n[i], n[i + 1], n[i + 2]))
                    if len(tris) >= cap:
                        return tris
            elif int(etype) == 3:
                for i in range(0, len(n) - 3, 4):
                    tris.append(_tri(pos, n[i], n[i + 1], n[i + 2]))
                    tris.append(_tri(pos, n[i], n[i + 2], n[i + 3]))
                    if len(tris) >= cap:
                        return tris
        if not tris:
            raise RuntimeError("STEP открылся, но сетка пустая.")
        return tris
    finally:
        try:
            gmsh.finalize()
        except Exception:
            pass


def write_binary_stl(path: Path, tris: list[tuple]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as fh:
        fh.write(b"AURA PLM MESH".ljust(80, b"\0"))
        fh.write(struct.pack("<I", len(tris)))
        for t in tris:
            fh.write(struct.pack(
                "<12fH",
                t[9], t[10], t[11],
                t[0], t[1], t[2],
                t[3], t[4], t[5],
                t[6], t[7], t[8],
                0,
            ))


def _cache_stl_path(path: Path) -> Path:
    st = path.stat()
    key = f"{path.resolve()}|{st.st_mtime_ns}|{st.st_size}"
    name = hashlib.md5(key.encode("utf-8", errors="ignore")).hexdigest() + ".stl"
    return _CACHE_DIR / name


def cached_mesh_path(path: Path) -> Path | None:
    ext = path.suffix.lower()
    if ext == ".stl" and path.exists():
        return path
    cache = _cache_stl_path(path)
    if cache.exists() and path.exists() and cache.stat().st_mtime >= path.stat().st_mtime:
        return cache
    return None


def load_model(path: Path) -> list[tuple]:
    ext = path.suffix.lower()
    if ext == ".stl":
        return load_stl(path)
    if ext not in {".step", ".stp", ".stpz"}:
        raise ValueError(f"Формат не поддерживается: {ext}. Нужен STEP или STL.")
    cache = cached_mesh_path(path)
    if cache is not None:
        return load_stl(cache)
    dst = _cache_stl_path(path)
    if getattr(sys, "_aura_in_worker", False):
        tris = tessellate_step(path)
        write_binary_stl(dst, tris)
        return tris
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "-m", "aura.view3d", str(path), str(dst)]
    subprocess.check_call(cmd, cwd=str(Path(__file__).resolve().parents[1]))
    if not dst.exists():
        raise RuntimeError("Не удалось построить сетку STEP.")
    return load_stl(dst)


class ModelViewer(tk.Toplevel):
    def __init__(self, master, path: Path, title: str | None = None):
        super().__init__(master)
        kind = path.suffix.lower().lstrip(".").upper() or "3D"
        self.title(title or f"AURA 3D — {path.name}")
        self.configure(bg=WORK)
        self.geometry("900x640")
        self.path = path
        self.tris: list[tuple] = []
        self.ax = 0.7
        self.ay = 0.55
        self.zoom = 1.0
        self._drag = None
        self.cx = self.cy = self.cz = 0.0
        self.scale0 = 1.0

        bar = tk.Frame(self, bg=NAVY)
        bar.pack(fill="x")
        self.caption = tk.Label(
            bar, text=f"{kind}  ·  {path.name}  ·  загрузка…",
            bg=NAVY, fg="#fff", font=("Segoe UI", 10, "bold"),
        )
        self.caption.pack(side="left", padx=12, pady=8)
        tk.Label(bar, text="ЛКМ — вращать, колесо — масштаб", bg=NAVY, fg="#A9C4DA", font=("Segoe UI", 8)).pack(
            side="right", padx=12
        )
        self.canvas = tk.Canvas(self, bg="#1A2330", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.status = tk.Label(self, text="Строим сетку…", bg=WORK, fg=TEXT, font=("Segoe UI", 9))
        self.status.pack(fill="x", pady=4)
        self.canvas.bind("<ButtonPress-1>", self._down)
        self.canvas.bind("<B1-Motion>", self._move)
        self.canvas.bind("<MouseWheel>", self._wheel)
        self.canvas.bind("<Configure>", lambda _e: self.redraw())
        tk.Button(
            bar, text="Вписать", command=self.fit, bg="#2C5282", fg="#fff",
            relief="flat", font=("Segoe UI", 8), cursor="hand2",
        ).pack(side="right", padx=(0, 8), pady=6, ipadx=8)
        self.after(40, self._load_async)

    def _load_async(self):
        def work():
            try:
                tris = load_model(self.path)
                err = None
            except Exception as exc:
                tris, err = [], exc
            self.after(0, lambda: self._loaded(tris, err))

        threading.Thread(target=work, daemon=True).start()

    def _loaded(self, tris, err):
        if not self.winfo_exists():
            return
        if err:
            self.status.configure(text=f"Не удалось открыть модель: {err}")
            self.caption.configure(text=f"{self.path.name}  ·  ошибка")
            return
        if not tris:
            self.status.configure(text="В модели нет треугольников.")
            return
        self.tris = tris
        self._center_scale()
        kind = self.path.suffix.lower().lstrip(".").upper()
        self.caption.configure(text=f"{kind}  ·  {self.path.name}  ·  {len(self.tris)} гран.")
        self.status.pack_forget()
        self.redraw()

    def fit(self):
        self.zoom = 1.0
        self.ax = 0.7
        self.ay = 0.55
        self.redraw()

    def _center_scale(self):
        xs, ys, zs = [], [], []
        for t in self.tris:
            xs += [t[0], t[3], t[6]]
            ys += [t[1], t[4], t[7]]
            zs += [t[2], t[5], t[8]]
        self.cx = (min(xs) + max(xs)) / 2
        self.cy = (min(ys) + max(ys)) / 2
        self.cz = (min(zs) + max(zs)) / 2
        span = max(max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs), 1e-6)
        self.scale0 = 2.2 / span

    def _down(self, e):
        self._drag = (e.x, e.y, self.ax, self.ay)

    def _move(self, e):
        if not self._drag:
            return
        x0, y0, ax, ay = self._drag
        self.ay = ay + (e.x - x0) * 0.01
        self.ax = ax + (e.y - y0) * 0.01
        self.redraw()

    def _wheel(self, e):
        self.zoom *= 1.1 if e.delta > 0 else 0.9
        self.zoom = max(0.2, min(8.0, self.zoom))
        self.redraw()

    def _rot(self, x, y, z):
        x -= self.cx
        y -= self.cy
        z -= self.cz
        cy, sy = math.cos(self.ay), math.sin(self.ay)
        x, z = x * cy - z * sy, x * sy + z * cy
        cx, sx = math.cos(self.ax), math.sin(self.ax)
        y, z = y * cx - z * sx, y * sx + z * cx
        return x, y, z

    def redraw(self):
        if not self.tris:
            return
        c = self.canvas
        c.delete("all")
        w = c.winfo_width() or 800
        h = c.winfo_height() or 560
        s = min(w, h) * 0.42 * self.zoom * self.scale0
        ox, oy = w / 2, h / 2
        faces = []
        light = (0.45, 0.55, 0.7)
        ln = math.sqrt(sum(v * v for v in light)) or 1
        lx, ly, lz = light[0] / ln, light[1] / ln, light[2] / ln
        for t in self.tris:
            x1, y1, z1 = self._rot(t[0], t[1], t[2])
            x2, y2, z2 = self._rot(t[3], t[4], t[5])
            x3, y3, z3 = self._rot(t[6], t[7], t[8])
            ax, ay, az = x2 - x1, y2 - y1, z2 - z1
            bx, by, bz = x3 - x1, y3 - y1, z3 - z1
            nx, ny, nz = ay * bz - az * by, az * bx - ax * bz, ax * by - ay * bx
            nd = math.sqrt(nx * nx + ny * ny + nz * nz) or 1
            nx, ny, nz = nx / nd, ny / nd, nz / nd
            if nz < 0:
                continue
            shade = max(0.18, min(1.0, 0.25 + 0.85 * (nx * lx + ny * ly + nz * lz)))
            zavg = (z1 + z2 + z3) / 3
            faces.append((zavg, x1, y1, x2, y2, x3, y3, shade))
        faces.sort(key=lambda f: f[0])
        step = max(1, len(faces) // 14000)
        for i, (_z, x1, y1, x2, y2, x3, y3, shade) in enumerate(faces):
            if i % step:
                continue
            r = int(185 * shade)
            g = int(178 * shade)
            b = int(155 * shade)
            color = f"#{r:02x}{g:02x}{b:02x}"
            c.create_polygon(
                ox + x1 * s, oy - y1 * s,
                ox + x2 * s, oy - y2 * s,
                ox + x3 * s, oy - y3 * s,
                fill=color, outline="",
            )


StlViewer = ModelViewer


def open_model(master, path: Path, title: str | None = None):
    return ModelViewer(master, path, title)


def draw_mesh_preview(canvas: tk.Canvas, tris: list[tuple], ax=0.7, ay=0.55) -> None:
    if not tris:
        return
    xs, ys, zs = [], [], []
    for t in tris:
        xs += [t[0], t[3], t[6]]
        ys += [t[1], t[4], t[7]]
        zs += [t[2], t[5], t[8]]
    cx = (min(xs) + max(xs)) / 2
    cy = (min(ys) + max(ys)) / 2
    cz = (min(zs) + max(zs)) / 2
    span = max(max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs), 1e-6)
    w = int(canvas.winfo_width() or 180)
    h = int(canvas.winfo_height() or 200)
    s = min(w, h) * 0.42 * (2.2 / span)
    ox, oy = w / 2, h / 2
    cy_, sy_ = math.cos(ay), math.sin(ay)
    cx_, sx_ = math.cos(ax), math.sin(ax)

    def rot(x, y, z):
        x, y, z = x - cx, y - cy, z - cz
        x, z = x * cy_ - z * sy_, x * sy_ + z * cy_
        y, z = y * cx_ - z * sx_, y * sx_ + z * cx_
        return x, y, z

    sample = tris[:: max(1, len(tris) // 2500)]
    faces = []
    for t in sample:
        x1, y1, z1 = rot(t[0], t[1], t[2])
        x2, y2, z2 = rot(t[3], t[4], t[5])
        x3, y3, z3 = rot(t[6], t[7], t[8])
        ax1, ay1, az1 = x2 - x1, y2 - y1, z2 - z1
        bx, by, bz = x3 - x1, y3 - y1, z3 - z1
        nx, ny, nz = ay1 * bz - az1 * by, az1 * bx - ax1 * bz, ax1 * by - ay1 * bx
        nd = math.sqrt(nx * nx + ny * ny + nz * nz) or 1
        nz /= nd
        if nz < 0:
            continue
        shade = max(0.2, min(1.0, 0.3 + 0.8 * nz))
        faces.append(((z1 + z2 + z3) / 3, x1, y1, x2, y2, x3, y3, shade))
    faces.sort(key=lambda f: f[0])
    canvas.delete("mesh")
    for _z, x1, y1, x2, y2, x3, y3, shade in faces:
        r = int(90 + 90 * shade)
        g = int(110 + 80 * shade)
        b = int(140 + 70 * shade)
        canvas.create_polygon(
            ox + x1 * s, oy - y1 * s,
            ox + x2 * s, oy - y2 * s,
            ox + x3 * s, oy - y3 * s,
            fill=f"#{r:02x}{g:02x}{b:02x}", outline="", tags="mesh",
        )


def load_model_quiet(path: Path) -> list[tuple]:
    hit = cached_mesh_path(path)
    if hit:
        return load_stl(hit)
    return load_model(path)


if __name__ == "__main__":
    sys._aura_in_worker = True  # type: ignore[attr-defined]
    src = Path(sys.argv[1])
    dst = Path(sys.argv[2])
    mesh = tessellate_step(src)
    write_binary_stl(dst, mesh)
