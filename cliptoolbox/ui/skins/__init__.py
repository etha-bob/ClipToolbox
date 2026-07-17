"""Skin registry.

A skin is a flat module of UPPERCASE design tokens (palette, geometry,
style switches, typeface preferences). cliptoolbox.ui.theme resolves one
skin at import time and republishes its tokens, so the rest of the UI keeps
reading `theme.X` and never needs to know which skin is active.

halo2 is the schema of record: get() refuses a skin that is missing any of
its token names, so a new skin fails loudly at startup instead of crashing
mid-render.
"""
from types import ModuleType

from cliptoolbox.ui.skins import halo2, reach

DEFAULT = "halo2"

_REGISTRY: dict[str, ModuleType] = {
    "halo2": halo2,
    "reach": reach,
}

_ALIASES = {
    "halo 2": "halo2",
    "halo_2": "halo2",
    "h2": "halo2",
    "halo reach": "reach",
    "halo_reach": "reach",
    "halo-reach": "reach",
    "haloreach": "reach",
}

TOKEN_NAMES = frozenset(name for name in vars(halo2) if name.isupper())


def normalize(skin_id) -> str:
    """Map user/config input to a registered skin id; unknown -> DEFAULT."""
    key = str(skin_id or "").strip().lower()
    key = _ALIASES.get(key, key)
    return key if key in _REGISTRY else DEFAULT


def get(skin_id) -> ModuleType:
    module = _REGISTRY[normalize(skin_id)]
    missing = TOKEN_NAMES - {name for name in vars(module) if name.isupper()}
    if missing:
        raise RuntimeError(
            f"skin '{module.SKIN_ID}' is missing tokens: {', '.join(sorted(missing))}")
    return module


def available() -> list[tuple[str, str]]:
    """(id, label) pairs for the settings UI, default first."""
    return [(skin_id, module.SKIN_LABEL) for skin_id, module in _REGISTRY.items()]
