"""
Pluggable data-export system.

Exporters convert the final workflow results into external formats
(e.g. ISAAC AI-Ready records).  The active exporter is selected by the
``EXPORT_FORMAT`` environment variable.

Public API
----------
get_exporter()         – return the configured exporter (or *None*)
is_export_available()  – quick check used by the web UI to show/hide the button
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from .base import BaseExporter, ExportResult  # noqa: F401

logger = logging.getLogger(__name__)

# Registry: format name → (module_path, class_name)
_REGISTRY: dict[str, tuple[str, str]] = {
    "isaac": ("aure.exporters.isaac", "IsaacExporter"),
}


def get_exporter() -> Optional[BaseExporter]:
    """Return the exporter configured via ``EXPORT_FORMAT``, or *None*."""
    fmt = (os.environ.get("EXPORT_FORMAT") or "").strip().lower()
    if not fmt:
        return None

    entry = _REGISTRY.get(fmt)
    if entry is None:
        logger.warning("[EXPORT] Unknown export format: %s", fmt)
        return None

    module_path, class_name = entry
    try:
        import importlib

        mod = importlib.import_module(module_path)
        cls = getattr(mod, class_name)
        return cls()
    except Exception as exc:
        logger.warning(
            "[EXPORT] Could not load exporter %s.%s: %s",
            module_path,
            class_name,
            exc,
        )
        return None


def is_export_available() -> bool:
    """Return *True* when a valid exporter is configured and loadable."""
    return get_exporter() is not None
