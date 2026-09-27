from pathlib import Path

import cv2
import numpy as np

from src.pipeline import ScanOptions, process_image


def test_pipeline_detects_synthetic_document(tmp_path: Path) -> None:
    image = np.full((720, 1080, 3), 80, dtype=np.uint8)
    document = np.full((360, 700, 3), 245, dtype=np.uint8)
    cv2.rectangle(document, (0, 0), (699, 359), (20, 20, 20), 5)
    image[180:540, 190:890] = document
    input_path = tmp_path / "document.jpg"
    cv2.imwrite(str(input_path), image)
    result = process_image(
        input_path,
        tmp_path / "outputs",
        "test-job",
        ScanOptions(cpp_acceleration=False),
    )
    assert result["document_detected"] is True
    assert result["detection_area_ratio"] > 0.2
    assert Path(tmp_path / "outputs" / "test-job" / "metadata.json").exists()
    assert Path(tmp_path / "outputs" / "test-job" / "processed" / "enhanced_document.jpg").exists()


def test_pipeline_handles_missing_document(tmp_path: Path) -> None:
    image = np.full((640, 900, 3), 128, dtype=np.uint8)
    input_path = tmp_path / "empty.jpg"
    cv2.imwrite(str(input_path), image)
    result = process_image(
        input_path,
        tmp_path / "outputs",
        "empty-job",
        ScanOptions(cpp_acceleration=False),
    )
    assert result["document_detected"] is False
    assert result["processing_time_ms"] >= 0
