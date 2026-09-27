"""Static guarantees that the extraction cannot be fitted to the benchmark."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEAKAGE_GUARD = ROOT / "scripts" / "check_dataset_leakage.py"


def test_extraction_source_contains_no_dataset_answers() -> None:
    """No dataset proper nouns, emails or long digit runs may appear in src/."""
    completed = subprocess.run(
        [sys.executable, str(LEAKAGE_GUARD)],
        capture_output=True,
        text=True,
        check=False,
        cwd=ROOT,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_confidence_is_derived_not_declared() -> None:
    """Field confidence must be computed, so the module cannot hold fixed literals."""
    source = (ROOT / "src" / "field_parser.py").read_text(encoding="utf-8")
    assert "TIER_WEIGHT" in source
    assert "consensus" in source
    forbidden = ('_field("name", name, 0.74', '_field("company", company, 0.78')
    for snippet in forbidden:
        assert snippet not in source, "hardcoded per-field confidence reintroduced"
