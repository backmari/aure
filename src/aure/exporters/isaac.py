"""
ISAAC AI-Ready Data exporter.

Assembles a manifest YAML file, copies the reduced data and best-fit model
JSON into an ``ai-ready-data/`` subdirectory, generates an LLM-powered
context description, then runs ``nr-isaac-format convert`` + ``validate``
to produce a validated ISAAC JSON record.
"""

from __future__ import annotations

import hashlib
import logging
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, List, Optional

from .base import BaseExporter, ExportResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Environment classification (mirrors IsaacWriter._classify_environment)
# ---------------------------------------------------------------------------

_ENVIRONMENT_KEYWORDS: list[tuple[str, str]] = [
    ("electrochemical", "operando"),
    ("operando", "operando"),
    ("under bias", "operando"),
    ("in situ", "in_situ"),
    ("in_situ", "in_situ"),
    ("in silico", "in_silico"),
    ("simulat", "in_silico"),
]


def _classify_environment(text: str) -> str:
    """Best-effort classification of free-text to the ISAAC environment enum."""
    low = text.strip().lower()
    for keyword, env in _ENVIRONMENT_KEYWORDS:
        if keyword in low:
            return env
    return "ex_situ"


# ---------------------------------------------------------------------------
# LLM context generation
# ---------------------------------------------------------------------------

_CONTEXT_PROMPT_TEMPLATE = """\
You are a scientific data curator.  Summarise the following neutron
reflectometry analysis session into a single concise paragraph suitable
for a metadata record.  The paragraph should describe:
- The sample (composition, structure, substrate, ambient medium)
- The measurement technique and conditions
- Key analysis results (final chi-squared, number of layers, notable findings)

Keep it factual and under 200 words.  Do NOT use bullet points and do NOT
include headings.

## Sample Description
{sample_description}

## Hypothesis
{hypothesis}

## Final Fit
chi² = {chi2}
Parameters:
{param_summary}

## Conversation Highlights
{messages_summary}
"""


def _generate_context_description(state: dict) -> str:
    """Use the LLM to generate a context paragraph from the workflow state.

    Falls back to ``state["sample_description"]`` if the LLM is unavailable.
    """
    sample_description = state.get("sample_description", "Not specified")
    hypothesis = state.get("hypothesis") or "None provided"
    fallback = sample_description

    # Collect final fit info
    fit_results = state.get("fit_results") or []
    chi2 = state.get("current_chi2") or state.get("best_chi2") or "N/A"
    param_summary = "N/A"
    if fit_results:
        latest = fit_results[-1]
        params = latest.get("parameters", {})
        if params:
            lines = [f"  {k}: {v}" for k, v in list(params.items())[:15]]
            param_summary = "\n".join(lines)

    # Summarise messages (keep it short — last 10 non-system messages)
    messages = state.get("messages") or []
    relevant = [m for m in messages if m.get("role") in ("user", "assistant")][-10:]
    if relevant:
        msg_lines = [f"  [{m['role']}] {m['content'][:300]}" for m in relevant]
        messages_summary = "\n".join(msg_lines)
    else:
        messages_summary = "No conversation recorded."

    prompt = _CONTEXT_PROMPT_TEMPLATE.format(
        sample_description=sample_description,
        hypothesis=hypothesis,
        chi2=chi2,
        param_summary=param_summary,
        messages_summary=messages_summary,
    )

    try:
        from ..llm import get_llm, invoke_with_timeout

        llm = get_llm(temperature=0)
        response = invoke_with_timeout(llm, prompt, timeout_seconds=60)
        text = (
            response.content.strip()
            if hasattr(response, "content")
            else str(response).strip()
        )
        if text:
            return text
    except Exception as exc:
        logger.warning("[ISAAC-EXPORT] LLM context generation failed: %s", exc)

    return fallback


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_run_name(data_file: str) -> str:
    """Derive a short run identifier from the data file path."""
    stem = Path(data_file).stem
    m = re.search(r"(\d{6})", stem)
    if m:
        return m.group(1)
    return re.sub(r"[^\w\-]", "_", stem)


def _find_best_problem_json(output_dir: Path) -> Optional[Path]:
    """Locate the best-fit ``problem.json`` in the output directory."""
    # Prefer the top-level copy made by _copy_best_problem_json
    top = output_dir / "problem.json"
    if top.exists():
        return top

    # Fall back: find the latest refl1d_output/fit_iter*/ directory
    refl1d_dir = output_dir / "refl1d_output"
    if refl1d_dir.is_dir():
        fit_dirs = sorted(refl1d_dir.glob("fit_iter*"))
        for d in reversed(fit_dirs):
            pj = d / "problem.json"
            if pj.exists():
                return pj

    return None


def _file_sha256(path: Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return ""


# ---------------------------------------------------------------------------
# IsaacExporter
# ---------------------------------------------------------------------------


class IsaacExporter(BaseExporter):
    """Export workflow results to ISAAC AI-Ready Record format."""

    @property
    def name(self) -> str:
        return "ISAAC AI-Ready Format"

    @property
    def format_id(self) -> str:
        return "isaac"

    def export(
        self,
        output_dir: Path,
        state: dict,
        run_info: dict,
        user_context: Optional[str] = None,
    ) -> ExportResult:
        errors: List[str] = []
        warnings: List[str] = []

        ai_dir = output_dir / "ai-ready-data"
        ai_dir.mkdir(parents=True, exist_ok=True)

        # ------------------------------------------------------------------
        # Step A – copy reduced data file
        # ------------------------------------------------------------------
        data_file_str = state.get("data_file") or run_info.get("data_file", "")
        data_file = Path(data_file_str) if data_file_str else None
        copied_data: Optional[Path] = None

        if data_file and data_file.is_file():
            copied_data = ai_dir / data_file.name
            shutil.copy2(data_file, copied_data)
            logger.info("[ISAAC-EXPORT] Copied data file → %s", copied_data)
        else:
            errors.append(f"Data file not found: {data_file_str}")

        # ------------------------------------------------------------------
        # Step B – copy best-fit model JSON
        # ------------------------------------------------------------------
        problem_json = _find_best_problem_json(output_dir)
        copied_model: Optional[Path] = None

        if problem_json:
            copied_model = ai_dir / "problem.json"
            shutil.copy2(problem_json, copied_model)
            logger.info("[ISAAC-EXPORT] Copied model JSON → %s", copied_model)
        else:
            warnings.append(
                "Best-fit problem.json not found; manifest will omit the model reference."
            )

        # ------------------------------------------------------------------
        # Step C – generate LLM context description
        # ------------------------------------------------------------------
        context_description = _generate_context_description(state)
        if user_context:
            context_description = user_context + "\n\n" + context_description
        context_file = ai_dir / "context.txt"
        context_file.write_text(context_description, encoding="utf-8")
        logger.info("[ISAAC-EXPORT] Wrote context description → %s", context_file)

        # ------------------------------------------------------------------
        # Step D – write manifest YAML
        # ------------------------------------------------------------------
        if errors:
            return ExportResult(
                success=False, output_path=ai_dir, errors=errors, warnings=warnings
            )

        manifest_path = ai_dir / "manifest.yaml"
        self._write_manifest(
            manifest_path=manifest_path,
            state=state,
            run_info=run_info,
            copied_data=copied_data,
            copied_model=copied_model,
            context_description=context_description,
        )
        logger.info("[ISAAC-EXPORT] Wrote manifest → %s", manifest_path)

        # ------------------------------------------------------------------
        # Step E – run nr-isaac-format convert
        # ------------------------------------------------------------------
        convert_ok = self._run_convert(manifest_path, warnings)

        # ------------------------------------------------------------------
        # Step F – validate the produced record(s)
        # ------------------------------------------------------------------
        if convert_ok:
            self._run_validate(ai_dir / "output", warnings)

        return ExportResult(
            success=len(errors) == 0,
            output_path=ai_dir,
            errors=errors,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # Manifest writer
    # ------------------------------------------------------------------

    def _write_manifest(
        self,
        manifest_path: Path,
        state: dict,
        run_info: dict,
        copied_data: Optional[Path],
        copied_model: Optional[Path],
        context_description: str,
    ) -> None:
        """Write a manifest YAML compatible with ``nr-isaac-format convert``."""
        import yaml

        sample_desc = (
            state.get("sample_description")
            or run_info.get("sample_description")
            or "Unknown sample"
        )
        data_file = state.get("data_file") or run_info.get("data_file", "")
        run_name = _extract_run_name(data_file)
        environment = _classify_environment(sample_desc)

        # Build measurement entry
        measurement: dict[str, Any] = {
            "name": f"Run {run_name}" if run_name else "Measurement",
            "reduced": f"./{copied_data.name}" if copied_data else "",
            "environment": environment,
            "context": context_description,
        }

        if copied_model:
            measurement["model"] = f"./{copied_model.name}"
            measurement["model_dataset_index"] = 1

        # Build sample block
        sample_block: dict[str, Any] = {
            "description": sample_desc,
        }
        if copied_model:
            sample_block["model"] = f"./{copied_model.name}"
            sample_block["model_dataset_index"] = 1

        manifest: dict[str, Any] = {
            "title": f"AuRE analysis — {sample_desc[:80]}",
            "sample": sample_block,
            "output": "./output",
            "measurements": [measurement],
        }

        manifest_path.write_text(
            yaml.dump(
                manifest, default_flow_style=False, sort_keys=False, allow_unicode=True
            ),
            encoding="utf-8",
        )

    # ------------------------------------------------------------------
    # nr-isaac-format CLI wrappers
    # ------------------------------------------------------------------

    def _run_convert(self, manifest_path: Path, warnings: list[str]) -> bool:
        """Run ``nr-isaac-format convert <manifest>``."""
        cmd = self._find_cli_command()
        if cmd is None:
            warnings.append(
                "nr-isaac-format is not installed. "
                "Install with: pip install 'aure[export]' or "
                "pip install git+https://github.com/isaac-neutrons/nr-isaac-format.git"
            )
            return False
        try:
            result = subprocess.run(
                [*cmd, "convert", manifest_path.name],
                capture_output=True,
                text=True,
                cwd=str(manifest_path.parent),
                timeout=120,
            )
            if result.returncode != 0:
                msg = result.stderr.strip() or result.stdout.strip()
                warnings.append(f"nr-isaac-format convert failed: {msg}")
                logger.warning("[ISAAC-EXPORT] convert failed: %s", msg)
                return False
            logger.info("[ISAAC-EXPORT] convert succeeded:\n%s", result.stdout.strip())
            return True
        except subprocess.TimeoutExpired:
            warnings.append("nr-isaac-format convert timed out after 120 s")
            return False
        except Exception as exc:
            warnings.append(f"nr-isaac-format convert error: {exc}")
            return False

    def _run_validate(self, output_dir: Path, warnings: list[str]) -> bool:
        """Run ``nr-isaac-format validate`` on each JSON in the output dir."""
        if not output_dir.is_dir():
            return False

        json_files = sorted(output_dir.glob("*.json"))
        if not json_files:
            warnings.append("No ISAAC JSON records found to validate.")
            return False

        cmd = self._find_cli_command()
        if cmd is None:
            warnings.append("nr-isaac-format CLI not found — skipping validation.")
            return False

        all_valid = True
        for jf in json_files:
            try:
                result = subprocess.run(
                    [*cmd, "validate", str(jf)],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if result.returncode != 0:
                    msg = result.stderr.strip() or result.stdout.strip()
                    warnings.append(f"Validation failed for {jf.name}: {msg}")
                    all_valid = False
                else:
                    logger.info("[ISAAC-EXPORT] Validated: %s", jf.name)
            except Exception as exc:
                warnings.append(f"Validation error for {jf.name}: {exc}")
                all_valid = False

        return all_valid

    # ------------------------------------------------------------------
    # CLI discovery
    # ------------------------------------------------------------------

    @staticmethod
    def _find_cli_command() -> Optional[list[str]]:
        """Locate the ``nr-isaac-format`` CLI entry-point.

        Returns a command list suitable for ``subprocess.run()``, or *None*
        if the tool is not installed.
        """
        import shutil

        # 1. Prefer the installed entry-point script
        exe = shutil.which("nr-isaac-format")
        if exe:
            return [exe]

        # 2. Try invoking via the package's cli module
        #    (works even without a __main__.py)
        try:
            from nr_isaac_format import cli as _cli  # noqa: F401

            return [
                sys.executable,
                "-c",
                "from nr_isaac_format.cli import main; main()",
            ]
        except ImportError:
            pass

        return None
