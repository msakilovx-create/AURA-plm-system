"""Каталог CAD-систем: расширения, процессы, реестр, COM."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class CadSystem:
    id: str
    name: str
    slot: str
    part_ext: tuple[str, ...]
    assembly_ext: tuple[str, ...]
    drawing_ext: tuple[str, ...] = ()
    processes: tuple[str, ...] = ()
    registry_hints: tuple[str, ...] = ()
    progids: tuple[str, ...] = ()
    exes: tuple[str, ...] = ()


CAD_SYSTEMS: tuple[CadSystem, ...] = (
    CadSystem(
        id="solidworks",
        name="SolidWorks",
        slot="sw",
        part_ext=(".sldprt",),
        assembly_ext=(".sldasm",),
        drawing_ext=(".slddrw",),
        processes=("SLDWORKS.exe", "SLDWORKS"),
        registry_hints=("SolidWorks", "SOLIDWORKS"),
        progids=("SldWorks.Application",),
        exes=("SLDWORKS.exe",),
    ),
    CadSystem(
        id="kompas",
        name="КОМПАС-3D",
        slot="native",
        part_ext=(".m3d",),
        assembly_ext=(".a3d",),
        drawing_ext=(".cdw", ".spw", ".frw"),
        processes=("KOMPAS.exe", "Kompas", "kStudy.exe"),
        registry_hints=("KOMPAS", "АСКОН", "ASCON"),
        progids=("KOMPAS.Application.7", "Kompas.Application.5"),
        exes=("KOMPAS.exe",),
    ),
    CadSystem(
        id="inventor",
        name="Autodesk Inventor",
        slot="native",
        part_ext=(".ipt",),
        assembly_ext=(".iam",),
        drawing_ext=(".idw", ".dwg"),
        processes=("Inventor.exe",),
        registry_hints=("Inventor",),
        progids=("Inventor.Application",),
        exes=("Inventor.exe",),
    ),
    CadSystem(
        id="solidedge",
        name="Solid Edge",
        slot="native",
        part_ext=(".par", ".psm"),
        assembly_ext=(".asm",),
        drawing_ext=(".dft",),
        processes=("Edge.exe", "SolidEdge.exe"),
        registry_hints=("Solid Edge",),
        progids=("SolidEdge.Application",),
        exes=("Edge.exe",),
    ),
    CadSystem(
        id="creo",
        name="PTC Creo",
        slot="native",
        part_ext=(".prt",),
        assembly_ext=(".asm",),
        drawing_ext=(".drw",),
        processes=("xtop.exe", "creo.exe", "parametric.exe"),
        registry_hints=("Creo", "Parametric"),
        progids=(),
        exes=("parametric.exe", "xtop.exe"),
    ),
    CadSystem(
        id="nx",
        name="Siemens NX",
        slot="native",
        part_ext=(".prt",),
        assembly_ext=(".prt",),
        drawing_ext=(),
        processes=("ugraf.exe", "ugs_router.exe"),
        registry_hints=("Siemens NX", "Unigraphics NX"),
        progids=(),
        exes=("ugraf.exe",),
    ),
    CadSystem(
        id="catia",
        name="CATIA",
        slot="native",
        part_ext=(".catpart",),
        assembly_ext=(".catproduct",),
        drawing_ext=(".catdrawing",),
        processes=("CNEXT.exe",),
        registry_hints=("CATIA V5", "CATIA V6", "CATIA.Application"),
        progids=("CATIA.Application",),
        exes=("CNEXT.exe",),
    ),
    CadSystem(
        id="tflex",
        name="T-FLEX CAD",
        slot="native",
        part_ext=(".grb",),
        assembly_ext=(".grb",),
        drawing_ext=(".grb",),
        processes=("TFlex.exe", "T-FLEX.exe"),
        registry_hints=("T-FLEX", "TFlex"),
        progids=("TFlex.Application",),
        exes=("TFlex.exe",),
    ),
    CadSystem(
        id="freecad",
        name="FreeCAD",
        slot="native",
        part_ext=(".fcstd",),
        assembly_ext=(".fcstd",),
        drawing_ext=(),
        processes=("FreeCAD.exe", "freecad.exe"),
        registry_hints=("FreeCAD",),
        progids=(),
        exes=("FreeCAD.exe",),
    ),
    CadSystem(
        id="autocad",
        name="AutoCAD",
        slot="native",
        part_ext=(".dwg", ".dxf"),
        assembly_ext=(),
        drawing_ext=(".dwg", ".dxf"),
        processes=("acad.exe",),
        registry_hints=("AutoCAD",),
        progids=("AutoCAD.Application",),
        exes=("acad.exe",),
    ),
    CadSystem(
        id="nanocad",
        name="nanoCAD",
        slot="native",
        part_ext=(".dwg", ".dxf"),
        assembly_ext=(),
        drawing_ext=(".dwg", ".dxf"),
        processes=("nCad.exe", "nanoCAD.exe"),
        registry_hints=("nanoCAD", "Нанософт"),
        progids=(),
        exes=("nCad.exe",),
    ),
    CadSystem(
        id="teamcenter",
        name="Siemens Teamcenter",
        slot="native",
        part_ext=(),
        assembly_ext=(),
        drawing_ext=(),
        processes=("Teamcenter.exe", "portal.exe", "TcServer.exe", "awclient.exe", "tcserver.exe"),
        registry_hints=("Siemens Teamcenter", "Teamcenter 1", "Teamcenter 2", "Teamcenter 4"),
        progids=(),
        exes=("Teamcenter.exe", "portal.exe"),
    ),
    CadSystem(
        id="step",
        name="STEP (нейтральный)",
        slot="stp",
        part_ext=(".stp", ".step", ".p21"),
        assembly_ext=(".stp", ".step", ".p21"),
        drawing_ext=(),
        processes=(),
        registry_hints=(),
        progids=(),
        exes=(),
    ),
)

_BY_ID = {s.id: s for s in CAD_SYSTEMS}


def get_system(system_id: str) -> CadSystem | None:
    return _BY_ID.get(system_id)


def all_cad_extensions() -> set[str]:
    exts: set[str] = {".pdf"}
    for sys in CAD_SYSTEMS:
        exts.update(sys.part_ext)
        exts.update(sys.assembly_ext)
        exts.update(sys.drawing_ext)
    return exts


def _norm_ext(path: str | Path) -> str:
    name = str(path).lower()
    # Creo versioned: name.prt.1
    for extra in (".1", ".2", ".3", ".4", ".5", ".6", ".7", ".8", ".9"):
        if name.endswith(extra):
            name = name[: -len(extra)]
            break
    suffix = Path(name).suffix.lower()
    return suffix


def classify_cad_file(path: str | Path) -> tuple[CadSystem | None, str]:
    """Вернуть (система, 'part'|'assembly'|'drawing'|'other')."""
    ext = _norm_ext(path)
    if ext == ".pdf":
        return None, "drawing"
    # Более специфичные системы раньше общих .prt/.asm/.dwg
    preferred = (
        "solidworks",
        "kompas",
        "inventor",
        "catia",
        "tflex",
        "freecad",
        "solidedge",
        "creo",
        "nx",
        "step",
        "autocad",
        "nanocad",
    )
    for sid in preferred:
        sys = _BY_ID[sid]
        if ext in sys.assembly_ext and ext not in sys.part_ext:
            return sys, "assembly"
        if ext in sys.part_ext and ext not in sys.assembly_ext:
            return sys, "part"
        if ext in sys.drawing_ext:
            return sys, "drawing"
        if ext in sys.assembly_ext:
            return sys, "assembly"
        if ext in sys.part_ext:
            return sys, "part"
    return None, "other"


def slot_for_path(path: str | Path) -> str:
    sys, kind = classify_cad_file(path)
    ext = _norm_ext(path)
    if ext in {".stp", ".step", ".p21"}:
        return "stp"
    if ext == ".pdf":
        return "pdf"
    if sys:
        return sys.slot
    return "native"


def file_dialog_filter() -> list[tuple[str, str]]:
    items = [
        ("CAD и STEP", "*.sldasm;*.sldprt;*.slddrw;*.a3d;*.m3d;*.cdw;*.iam;*.ipt;*.step;*.stp;*.CATProduct;*.CATPart;*.FCStd;*.par;*.asm"),
        ("SolidWorks", "*.sldasm;*.sldprt;*.slddrw"),
        ("КОМПАС-3D", "*.a3d;*.m3d;*.cdw;*.spw;*.frw"),
        ("Inventor", "*.iam;*.ipt;*.idw"),
        ("STEP", "*.step;*.stp"),
        ("Все файлы", "*.*"),
    ]
    return items
