import os

from cliptoolbox.core.paths import BASE_DIR, INTERNAL_DIR, RESOURCE_DIR

# ============================================================
# tkinterdnd2 setup
# ============================================================

TKDND_CANDIDATE_DIRS = [
    RESOURCE_DIR / "tkdnd2.8",
    RESOURCE_DIR / "tkinterdnd2" / "tkdnd",
    RESOURCE_DIR / "tkinterdnd2" / "tkdnd2.8",
    BASE_DIR / "tkdnd2.8",
    INTERNAL_DIR / "tkinterdnd2" / "tkdnd",
    INTERNAL_DIR / "tkinterdnd2" / "tkdnd2.8",
    INTERNAL_DIR / "tkdnd2.8",
]

for possible_tkdnd_dir in TKDND_CANDIDATE_DIRS:
    if possible_tkdnd_dir.exists():
        os.environ["TKDND_LIBRARY"] = str(possible_tkdnd_dir)
        break

try:
    from tkinterdnd2 import TkinterDnD, DND_FILES

    DND_AVAILABLE = True
except Exception:
    TkinterDnD = None
    DND_FILES = None
    DND_AVAILABLE = False
