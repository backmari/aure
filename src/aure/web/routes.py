"""Flask blueprint – page routes and JSON API endpoints."""

import os
import re
import threading
from pathlib import Path
from typing import Optional

from flask import (
    Blueprint,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

from .data import RunData

bp = Blueprint(
    "web",
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/web",
)


def _run_data() -> Optional[RunData]:
    output_dir = current_app.config.get("OUTPUT_DIR")
    if not output_dir or not Path(output_dir).exists():
        return None
    return RunData(output_dir)


def _has_output() -> bool:
    """Return True when a valid output directory is configured."""
    rd = _run_data()
    return rd is not None and bool(rd.get_run_info())


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _extract_run_name(data_file: str) -> str:
    """
    Derive a short run name from the data-file path.

    Looks for a 6-digit number first (e.g. ``REFL_218386_…``), then
    falls back to the filename stem.
    """
    stem = Path(data_file).stem
    m = re.search(r"(\d{6})", stem)
    if m:
        return m.group(1)
    # Sanitise the stem for use as a directory name
    return re.sub(r"[^\w\-]", "_", stem)


# ------------------------------------------------------------------
# Page routes
# ------------------------------------------------------------------


@bp.route("/")
def index():
    """Landing page – setup form or redirect to results."""
    output_dir = current_app.config.get("OUTPUT_DIR")
    run_state = current_app.config["RUN_STATE"]

    # If we have a pre-loaded output dir (legacy serve mode) redirect
    if output_dir and Path(output_dir).exists() and run_state["status"] == "idle":
        ri = _run_data()
        if ri and ri.get_run_info():
            return redirect(url_for("web.history"))

    return render_template("setup.html", active_tab="setup", run_state=run_state)


@bp.route("/history")
def history():
    if not _has_output():
        flash("No analysis results yet – start one first.", "warning")
        return redirect(url_for("web.index"))
    rd = _run_data()
    return render_template(
        "history.html",
        run_info=rd.get_run_info(),
        active_tab="history",
    )


@bp.route("/results")
def results():
    if not _has_output():
        flash("No analysis results yet – start one first.", "warning")
        return redirect(url_for("web.index"))
    rd = _run_data()
    return render_template(
        "results.html",
        run_info=rd.get_run_info(),
        active_tab="results",
    )


# ------------------------------------------------------------------
# JSON API – existing data endpoints
# ------------------------------------------------------------------


@bp.route("/api/run-info")
def api_run_info():
    rd = _run_data()
    if not rd:
        return jsonify({})
    return jsonify(rd.get_run_info())


@bp.route("/api/chi2")
def api_chi2():
    rd = _run_data()
    if not rd:
        return jsonify([])
    return jsonify(rd.get_chi2_progression())


@bp.route("/api/reflectivity")
def api_reflectivity():
    rd = _run_data()
    if not rd:
        return jsonify({"Q": [], "R": [], "dR": [], "models": []})
    return jsonify(rd.get_reflectivity_data())


@bp.route("/api/sld")
def api_sld():
    rd = _run_data()
    if not rd:
        return jsonify({"profiles": []})
    return jsonify(rd.get_sld_profiles())


@bp.route("/api/parameters")
def api_parameters():
    rd = _run_data()
    if not rd:
        return jsonify({"parameters": []})
    return jsonify(rd.get_fit_parameters())


@bp.route("/api/llm-status")
def api_llm_status():
    rd = _run_data()
    if not rd:
        return jsonify({"total": 0, "succeeded": 0, "failed": 0, "used_fallback": 0, "all_ok": True, "calls": []})
    return jsonify(rd.get_llm_summary())


# ------------------------------------------------------------------
# JSON API – server-side file / folder browsing
# ------------------------------------------------------------------


def _safe_path(raw: str) -> Optional[Path]:
    """Resolve and validate a path. Return None if unsafe."""
    try:
        p = Path(raw).expanduser().resolve()
        if not p.exists():
            return None
        return p
    except Exception:
        return None


@bp.route("/api/browse-files")
def api_browse_files():
    """
    List files and directories at a given path.

    Query params:
        path  – directory to list (default: home dir)
        ext   – optional extension filter, e.g. ".txt"
    """
    raw = request.args.get("path", str(Path.home()))
    ext = request.args.get("ext", "")
    target = _safe_path(raw)
    if target is None:
        return jsonify({"error": "Path does not exist"}), 400
    if not target.is_dir():
        target = target.parent

    entries = []
    try:
        for child in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            if child.name.startswith("."):
                continue
            if child.is_dir():
                entries.append({"name": child.name, "is_dir": True, "path": str(child)})
            elif not ext or child.suffix.lower() == ext.lower():
                entries.append({"name": child.name, "is_dir": False, "path": str(child)})
    except PermissionError:
        return jsonify({"error": "Permission denied"}), 403

    parent = str(target.parent) if target.parent != target else None
    return jsonify({"current": str(target), "parent": parent, "entries": entries})


@bp.route("/api/browse-dirs")
def api_browse_dirs():
    """
    List only directories at a given path (for the output-folder picker).

    Query params:
        path – directory to list (default: cwd)
    """
    raw = request.args.get("path", str(Path.cwd()))
    target = _safe_path(raw)
    if target is None:
        return jsonify({"error": "Path does not exist"}), 400
    if not target.is_dir():
        target = target.parent

    entries = []
    try:
        for child in sorted(target.iterdir(), key=lambda p: p.name.lower()):
            if child.name.startswith("."):
                continue
            if child.is_dir():
                entries.append({"name": child.name, "path": str(child)})
    except PermissionError:
        return jsonify({"error": "Permission denied"}), 403

    parent = str(target.parent) if target.parent != target else None
    return jsonify({"current": str(target), "parent": parent, "entries": entries})


# ------------------------------------------------------------------
# JSON API – analysis lifecycle
# ------------------------------------------------------------------


@bp.route("/api/start-analysis", methods=["POST"])
def api_start_analysis():
    """
    Launch a background analysis run.

    Expects JSON body::

        {
            "data_file": "/abs/path/to/data.txt",
            "sample_description": "...",
            "hypothesis": "...",       // optional
            "output_dir": "/abs/path"  // root output dir
        }
    """
    lock: threading.Lock = current_app.config["RUN_LOCK"]
    run_state: dict = current_app.config["RUN_STATE"]

    with lock:
        if run_state["status"] == "running":
            return jsonify({"error": "An analysis is already running"}), 409

    body = request.get_json(silent=True) or {}
    data_file = (body.get("data_file") or "").strip()
    sample_description = (body.get("sample_description") or "").strip()
    hypothesis = (body.get("hypothesis") or "").strip() or None
    output_root = (body.get("output_dir") or "").strip()

    # ---- Validation ------------------------------------------------
    errors = []
    if not data_file or not Path(data_file).is_file():
        errors.append("data_file: file does not exist")
    if not sample_description:
        errors.append("sample_description is required")
    if not output_root:
        errors.append("output_dir is required")
    if errors:
        return jsonify({"errors": errors}), 400

    # Determine run sub-directory
    run_name = _extract_run_name(data_file)
    output_dir = str(Path(output_root).expanduser().resolve() / run_name)
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Reset run state
    with lock:
        run_state.update({
            "status": "running",
            "output_dir": output_dir,
            "current_node": None,
            "iteration": 0,
            "checkpoints": [],
            "error": None,
        })

    # Store the Flask app reference for the background thread
    app = current_app._get_current_object()

    def _run_in_background():
        from ..workflow.runner import run_analysis as _run_analysis

        def _checkpoint_cb(state, node_name):
            with lock:
                run_state["current_node"] = node_name
                run_state["iteration"] = state.get("iteration", 0)
                # Compute LLM calls for this step by diffing cumulative list
                all_llm = state.get("llm_calls", [])
                prev_count = sum(len(cp.get("llm_calls", [])) for cp in run_state["checkpoints"])
                step_llm = all_llm[prev_count:]
                run_state["checkpoints"].append({
                    "node": node_name,
                    "chi2": state.get("current_chi2"),
                    "llm_calls": step_llm,
                })

        try:
            _run_analysis(
                data_file=data_file,
                sample_description=sample_description,
                hypothesis=hypothesis,
                output_dir=output_dir,
                checkpoint_callback=_checkpoint_cb,
            )
            with lock:
                run_state["status"] = "complete"
            # Update app config so history/results pages work
            app.config["OUTPUT_DIR"] = output_dir
        except Exception as exc:
            with lock:
                run_state["status"] = "error"
                run_state["error"] = str(exc)

    t = threading.Thread(target=_run_in_background, daemon=True)
    t.start()

    return jsonify({"status": "started", "output_dir": output_dir})


@bp.route("/api/analysis-status")
def api_analysis_status():
    """Return current analysis run state."""
    lock: threading.Lock = current_app.config["RUN_LOCK"]
    run_state: dict = current_app.config["RUN_STATE"]
    with lock:
        return jsonify(dict(run_state))
