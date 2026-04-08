from __future__ import annotations

import importlib.util
from pathlib import Path


_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_PROJECT_REWRITE = _PROJECT_ROOT / "rewrite.py"

_SPEC = importlib.util.spec_from_file_location(
    "wappkit_social_distributor_root_rewrite",
    _PROJECT_REWRITE,
)

if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"Unable to load project rewrite module from {_PROJECT_REWRITE}")

_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)

DevtoRewriter = _MODULE.DevtoRewriter

__all__ = ["DevtoRewriter"]
