"""Compatibility runner for the canonical pre-open test suite."""

from pathlib import Path
import runpy


runpy.run_path(str(Path(__file__).parent / "tests" / "test_preopen.py"), run_name="__main__")
