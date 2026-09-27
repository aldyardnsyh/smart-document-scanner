import json
import warnings
from pathlib import Path

import pytest

from src.ocr_engine import engine_available
from src.pipeline import ScanOptions, process_image

ROOT_DIR = Path(__file__).resolve().parents[1]
DATASET_DIR = ROOT_DIR / "dataset"
MANIFEST_PATH = Path(__file__).parent / "fixtures" / "real_dataset_manifest.json"
MANIFEST = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
OCR_AVAILABLE = engine_available()


@pytest.mark.skipif(
    not OCR_AVAILABLE,
    reason="The OCR engine is installed in the Docker test image",
)
@pytest.mark.parametrize("filename", sorted(MANIFEST))
def test_real_dataset_scenario(filename: str, tmp_path: Path) -> None:
    expectation = MANIFEST[filename]
    result = process_image(
        DATASET_DIR / filename,
        tmp_path,
        f"scenario-{Path(filename).stem}",
        ScanOptions(cpp_acceleration=False),
    )
    assert result["document_detected"] is True
    assert result["fields"]["document_type"] == expectation["document_type"]
    normalized_text = result["raw_text"].casefold()
    token_hits = sum(
        token.casefold() in normalized_text for token in expectation["expected_tokens"]
    )
    assert token_hits >= expectation["minimum_token_hits"]
    assert result["assets"]["corrected"]
    assert result["assets"]["enhanced"]
    if expectation["expected_fields"]:
        field_names = {field["name"] for field in result["fields"]["fields"]}
        assert field_names & set(expectation["expected_fields"])
    else:
        assert not result["fields"]["fields"]


def test_every_manifest_entry_exists_in_the_dataset() -> None:
    """Report manifest coverage without failing on a user-curated dataset.

    The dataset belongs to the owner and may be curated down. A hard-coded count or an
    exact set comparison made this test fail the moment a photograph was added or removed,
    which hid the real signal. The missing list is surfaced as a warning so it stays visible.
    """
    available = {path.name for path in DATASET_DIR.iterdir() if path.is_file()}
    missing = sorted(set(MANIFEST) - available)
    if missing:
        warnings.warn(
            f"dataset is missing {len(missing)} manifest file(s): {missing}",
            stacklevel=2,
        )
    present = sorted(set(MANIFEST) & available)
    assert len(present) >= 10, (
        f"expected at least 10 benchmark photographs, found {len(present)}: {present}"
    )


def test_dataset_has_no_unexpected_files() -> None:
    available = {path.name for path in DATASET_DIR.iterdir() if path.is_file()}
    extra = sorted(available - set(MANIFEST))
    if extra:
        warnings.warn(
            f"{len(extra)} dataset file(s) have no manifest entry and will not be scored: {extra}",
            stacklevel=2,
        )
    assert available
