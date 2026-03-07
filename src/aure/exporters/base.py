"""
Base class and result dataclass for data exporters.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class ExportResult:
    """Outcome of an export operation."""

    success: bool
    output_path: Optional[Path] = None
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class BaseExporter(abc.ABC):
    """Abstract interface that every exporter must implement."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Human-readable display name (shown in the web UI)."""

    @property
    @abc.abstractmethod
    def format_id(self) -> str:
        """Short machine identifier (matches ``EXPORT_FORMAT`` value)."""

    @abc.abstractmethod
    def export(
        self,
        output_dir: Path,
        state: dict,
        run_info: dict,
    ) -> ExportResult:
        """
        Perform the export.

        Parameters
        ----------
        output_dir:
            Root output directory for the current workflow run.
        state:
            The final workflow state dict (from ``final_state.json``).
        run_info:
            Contents of ``run_info.json``.

        Returns
        -------
        ExportResult with success flag, output path, and any errors/warnings.
        """
