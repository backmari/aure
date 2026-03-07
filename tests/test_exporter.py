"""
Tests for the data exporter system — base registry and ISAAC exporter.
"""

import json
import os
from unittest import mock

import pytest


# ---------------------------------------------------------------
# Registry tests
# ---------------------------------------------------------------


class TestExporterRegistry:
    """Tests for ``aure.exporters.get_exporter`` / ``is_export_available``."""

    def test_no_env_returns_none(self):
        from aure.exporters import get_exporter

        with mock.patch.dict(os.environ, {}, clear=True):
            os.environ.pop("EXPORT_FORMAT", None)
            assert get_exporter() is None

    def test_empty_env_returns_none(self):
        from aure.exporters import get_exporter

        with mock.patch.dict(os.environ, {"EXPORT_FORMAT": ""}):
            assert get_exporter() is None

    def test_unknown_format_returns_none(self):
        from aure.exporters import get_exporter

        with mock.patch.dict(os.environ, {"EXPORT_FORMAT": "unsupported_xyz"}):
            assert get_exporter() is None

    def test_isaac_format_returns_exporter(self):
        from aure.exporters import get_exporter

        with mock.patch.dict(os.environ, {"EXPORT_FORMAT": "isaac"}):
            exp = get_exporter()
            assert exp is not None
            assert exp.format_id == "isaac"
            assert exp.name == "ISAAC AI-Ready Format"

    def test_is_export_available_true(self):
        from aure.exporters import is_export_available

        with mock.patch.dict(os.environ, {"EXPORT_FORMAT": "isaac"}):
            assert is_export_available() is True

    def test_is_export_available_false(self):
        from aure.exporters import is_export_available

        with mock.patch.dict(os.environ, {}, clear=True):
            os.environ.pop("EXPORT_FORMAT", None)
            assert is_export_available() is False


# ---------------------------------------------------------------
# ISAAC exporter tests
# ---------------------------------------------------------------


def _make_state(output_dir: str, data_file: str) -> dict:
    """Build a minimal state dict resembling a completed workflow."""
    return {
        "data_file": data_file,
        "Q": [0.01, 0.02, 0.03, 0.04, 0.05],
        "R": [1.0, 0.8, 0.5, 0.2, 0.05],
        "dR": [0.01, 0.01, 0.01, 0.01, 0.005],
        "sample_description": "50 nm Cu on 5 nm Ti on Si substrate in dTHF",
        "hypothesis": "Copper layer with titanium adhesion layer",
        "parsed_sample": {
            "substrate": {"name": "silicon", "sld": 2.07, "roughness": 5.0},
            "layers": [
                {"name": "Ti", "sld": -1.95, "thickness": 50.0, "roughness": 5.0},
                {"name": "Cu", "sld": 6.55, "thickness": 500.0, "roughness": 8.0},
            ],
            "ambient": {"name": "dTHF", "sld": 6.36},
        },
        "current_chi2": 1.45,
        "best_chi2": 1.45,
        "fit_results": [
            {
                "iteration": 0,
                "method": "dream",
                "chi_squared": 1.45,
                "converged": True,
                "parameters": {
                    "Cu thickness": 502.3,
                    "Cu roughness": 8.1,
                    "Ti thickness": 48.7,
                },
                "uncertainties": {
                    "Cu thickness": 1.2,
                    "Cu roughness": 0.5,
                    "Ti thickness": 0.8,
                },
            }
        ],
        "messages": [
            {
                "role": "system",
                "content": "Data loaded successfully.",
                "timestamp": None,
            },
            {
                "role": "assistant",
                "content": "Building a 2-layer model: Cu/Ti on Si.",
                "timestamp": None,
            },
            {
                "role": "assistant",
                "content": "Fit converged with chi²=1.45.",
                "timestamp": None,
            },
        ],
        "output_dir": output_dir,
        "iteration": 1,
    }


def _make_run_info(data_file: str) -> dict:
    return {
        "run_id": "test_run_123",
        "started_at": "2026-03-07T10:00:00",
        "data_file": data_file,
        "sample_description": "50 nm Cu on 5 nm Ti on Si substrate in dTHF",
        "hypothesis": "Copper layer with titanium adhesion layer",
    }


class TestIsaacExporter:
    """Tests for ``aure.exporters.isaac.IsaacExporter``."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path):
        """Create a temporary output directory structure."""
        self.output_dir = tmp_path / "output"
        self.output_dir.mkdir()

        # Create a fake reduced data file
        self.data_file = tmp_path / "REFL_218386_combined_data_auto.txt"
        self.data_file.write_text(
            "# Run 218386\n# Q (1/Å)  R  dR\n0.01  1.0  0.01\n0.02  0.8  0.01\n"
        )

        # Create a fake problem.json (best-fit model)
        problem = {"$schema": "bumps-draft-03", "object": {"name": "test"}}
        (self.output_dir / "problem.json").write_text(json.dumps(problem))

        self.state = _make_state(str(self.output_dir), str(self.data_file))
        self.run_info = _make_run_info(str(self.data_file))

    def test_export_creates_ai_ready_dir(self):
        from aure.exporters.isaac import IsaacExporter

        exporter = IsaacExporter()
        # Mock the LLM call so tests don't require an API key
        with mock.patch(
            "aure.exporters.isaac._generate_context_description",
            return_value="Test context description for Cu/Ti/Si sample.",
        ):
            result = exporter.export(self.output_dir, self.state, self.run_info)

        ai_dir = self.output_dir / "ai-ready-data"
        assert ai_dir.is_dir()
        assert result.output_path == ai_dir

    def test_export_copies_data_file(self):
        from aure.exporters.isaac import IsaacExporter

        exporter = IsaacExporter()
        with mock.patch(
            "aure.exporters.isaac._generate_context_description",
            return_value="Test context.",
        ):
            exporter.export(self.output_dir, self.state, self.run_info)

        ai_dir = self.output_dir / "ai-ready-data"
        copied = ai_dir / self.data_file.name
        assert copied.is_file()
        assert copied.read_text() == self.data_file.read_text()

    def test_export_copies_model_json(self):
        from aure.exporters.isaac import IsaacExporter

        exporter = IsaacExporter()
        with mock.patch(
            "aure.exporters.isaac._generate_context_description",
            return_value="Test context.",
        ):
            exporter.export(self.output_dir, self.state, self.run_info)

        ai_dir = self.output_dir / "ai-ready-data"
        assert (ai_dir / "problem.json").is_file()

    def test_export_writes_context_txt(self):
        from aure.exporters.isaac import IsaacExporter

        exporter = IsaacExporter()
        ctx = "Generated context for neutron reflectometry analysis."
        with mock.patch(
            "aure.exporters.isaac._generate_context_description",
            return_value=ctx,
        ):
            exporter.export(self.output_dir, self.state, self.run_info)

        ai_dir = self.output_dir / "ai-ready-data"
        assert (ai_dir / "context.txt").is_file()
        assert (ai_dir / "context.txt").read_text() == ctx

    def test_export_writes_manifest_yaml(self):
        import yaml
        from aure.exporters.isaac import IsaacExporter

        exporter = IsaacExporter()
        with mock.patch(
            "aure.exporters.isaac._generate_context_description",
            return_value="Test context.",
        ):
            exporter.export(self.output_dir, self.state, self.run_info)

        manifest = self.output_dir / "ai-ready-data" / "manifest.yaml"
        assert manifest.is_file()

        data = yaml.safe_load(manifest.read_text())
        assert "title" in data
        assert "sample" in data
        assert "measurements" in data
        assert len(data["measurements"]) == 1

        m = data["measurements"][0]
        assert "reduced" in m
        assert "context" in m
        assert "environment" in m

    def test_export_manifest_sample_block(self):
        import yaml
        from aure.exporters.isaac import IsaacExporter

        exporter = IsaacExporter()
        with mock.patch(
            "aure.exporters.isaac._generate_context_description",
            return_value="Test context.",
        ):
            exporter.export(self.output_dir, self.state, self.run_info)

        manifest = self.output_dir / "ai-ready-data" / "manifest.yaml"
        data = yaml.safe_load(manifest.read_text())

        assert data["sample"]["description"] == self.state["sample_description"]
        assert "./problem.json" in data["sample"]["model"]

    def test_export_fails_with_missing_data_file(self):
        from aure.exporters.isaac import IsaacExporter

        self.state["data_file"] = "/nonexistent/file.txt"
        exporter = IsaacExporter()
        with mock.patch(
            "aure.exporters.isaac._generate_context_description",
            return_value="Test context.",
        ):
            result = exporter.export(self.output_dir, self.state, self.run_info)

        assert result.success is False
        assert any("not found" in e for e in result.errors)

    def test_export_warns_on_missing_model(self):
        from aure.exporters.isaac import IsaacExporter

        # Remove the problem.json
        (self.output_dir / "problem.json").unlink()

        exporter = IsaacExporter()
        with mock.patch(
            "aure.exporters.isaac._generate_context_description",
            return_value="Test context.",
        ):
            result = exporter.export(self.output_dir, self.state, self.run_info)

        assert any("problem.json" in w for w in result.warnings)

    def test_export_result_has_correct_output_path(self):
        from aure.exporters.isaac import IsaacExporter

        exporter = IsaacExporter()
        with mock.patch(
            "aure.exporters.isaac._generate_context_description",
            return_value="Test context.",
        ):
            result = exporter.export(self.output_dir, self.state, self.run_info)

        assert result.output_path == self.output_dir / "ai-ready-data"


# ---------------------------------------------------------------
# Environment classification
# ---------------------------------------------------------------


class TestEnvironmentClassification:
    def test_operando(self):
        from aure.exporters.isaac import _classify_environment

        assert _classify_environment("electrochemical cell") == "operando"
        assert _classify_environment("operando measurement") == "operando"

    def test_in_situ(self):
        from aure.exporters.isaac import _classify_environment

        assert _classify_environment("in situ heating") == "in_situ"

    def test_ex_situ_default(self):
        from aure.exporters.isaac import _classify_environment

        assert _classify_environment("50 nm Cu on Si") == "ex_situ"

    def test_in_silico(self):
        from aure.exporters.isaac import _classify_environment

        assert _classify_environment("simulation data") == "in_silico"


# ---------------------------------------------------------------
# LLM context generation
# ---------------------------------------------------------------


class TestContextGeneration:
    def test_fallback_on_llm_failure(self):
        from aure.exporters.isaac import _generate_context_description

        state = {
            "sample_description": "Test sample on silicon",
            "hypothesis": None,
            "current_chi2": 2.0,
            "fit_results": [],
            "messages": [],
        }

        # Mock LLM to raise an exception
        with mock.patch("aure.llm.get_llm", side_effect=Exception("No API key")):
            result = _generate_context_description(state)

        assert result == "Test sample on silicon"

    def test_uses_llm_response_when_available(self):
        from aure.exporters.isaac import _generate_context_description

        state = {
            "sample_description": "Cu on Si",
            "hypothesis": "Single Cu layer",
            "current_chi2": 1.5,
            "fit_results": [{"parameters": {"Cu thickness": 500}, "chi_squared": 1.5}],
            "messages": [
                {"role": "assistant", "content": "Model built.", "timestamp": None}
            ],
        }

        mock_response = mock.MagicMock()
        mock_response.content = "A neutron reflectometry study of Cu thin film on Si."

        mock_llm = mock.MagicMock()
        with mock.patch("aure.llm.get_llm", return_value=mock_llm):
            with mock.patch(
                "aure.llm.invoke_with_timeout",
                return_value=mock_response,
            ):
                result = _generate_context_description(state)

        assert "Cu" in result
        assert "Si" in result
