"""Связь AURA PLM с CAD-системами и выгрузка состава изделия."""

from .detect import detect_cad_systems
from .importing import (
    attach_cad_file,
    import_cad_source,
    import_from_running_cad,
    new_cad_link,
    open_in_cad,
    reveal_in_explorer,
    resync_link,
)
from .systems import CAD_SYSTEMS, classify_cad_file
from .teamcenter import import_teamcenter, looks_like_teamcenter

__all__ = [
    "CAD_SYSTEMS",
    "classify_cad_file",
    "attach_cad_file",
    "detect_cad_systems",
    "import_cad_source",
    "import_from_running_cad",
    "new_cad_link",
    "open_in_cad",
    "reveal_in_explorer",
    "resync_link",
    "import_teamcenter",
    "looks_like_teamcenter",
]
