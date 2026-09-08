"""Compatibility runner for the canonical decision-engine test suite."""

from pathlib import Path
import runpy


runpy.run_path(str(Path(__file__).parent / "tests" / "test_decision_engine.py"), run_name="__main__")
