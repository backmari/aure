"""
Flask web application for visualizing AuRE workflow results.

Usage:
    from aure.web import create_app
    app = create_app("/path/to/output")
    app.run(port=5000)

    # Interactive mode (no pre-existing output):
    app = create_app()
    app.run(port=5000)

Or via the CLI:
    aure serve ./output
    aure serve              # interactive setup mode
"""

import threading
from typing import Optional

from flask import Flask
from .routes import bp


def _default_run_state() -> dict:
    """Return a fresh run-state dict."""
    return {
        "status": "idle",  # idle | running | complete | error
        "output_dir": None,
        "current_node": None,
        "iteration": 0,
        "checkpoints": [],  # [{node, chi2, timestamp}]
        "error": None,
    }


def create_app(output_dir: Optional[str] = None) -> Flask:
    """
    Create the Flask application.

    Args:
        output_dir: Path to the workflow output directory.  When *None*
            the app starts in interactive setup mode – users can pick
            a data file, enter a sample description, and launch an
            analysis from the browser.

    Returns:
        Configured Flask application.
    """
    app = Flask(__name__)
    app.config["OUTPUT_DIR"] = output_dir
    app.config["RUN_STATE"] = _default_run_state()
    app.config["RUN_LOCK"] = threading.Lock()
    app.secret_key = "aure-interactive"  # needed for flash messages
    app.register_blueprint(bp)
    return app
