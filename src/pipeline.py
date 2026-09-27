import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from math import atan2, degrees
from pathlib import Path

import cv2
import numpy as np

from .detector import detect_document, draw_detection_debug, order_points
from .enhancer import enhance_image
from .field_parser import (
    CARD_LABELS,
    KTP_LABELS,
    PAPER_LABELS,
    RECEIPT_LABELS,
    Extraction,
    parse_all,
    summarise_confidence,
)
from .ocr_engine import OcrResult, run_ocr_variants
from .perspective import four_point_transform

# The number of distinct field types the parser can actually emit for each document type.
# This is the honest denominator for extraction coverage: a card is not "100% parsed" just
# because OCR was confident, and the caller deserves to see how much of the recognisable
# schema was really recovered.
RECOGNISED_FIELDS: dict[str, int] = {
    "business_card": len(CARD_LABELS),
    "id_card": len(KTP_LABELS),
    "receipt": len(RECEIPT_LABELS),
    "paper_document": len(PAPER_LABELS),
}

Image = np.ndarray
ProgressCallback = Callable[[str, int, str], None]


@dataclass(frozen=True)
class ScanOptions:
    document_type: str = "auto"
    fast_denoise: bool = False
    cpp_acceleration: bool = True
    ocr_language: str = "eng+ind"


def read_image(path: Path) -> Image:
    encoded = np.fromfile(str(path), dtype=np.uint8)
    image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Unsupported or corrupted image file")
    return image


def write_image(path: Path, image: Image) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    suffix = path.suffix or ".jpg"
    success, encoded = cv2.imencode(suffix, image)
    if not success:
        raise OSError(f"Could not encode image as {suffix}")
    encoded.tofile(str(path))


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary_path.replace(path)


def _notify(callback: ProgressCallback | None, stage: str, progress: int, message: str) -> None:
    if callback is not None:
        callback(stage, progress, message)


def _rotation_angle(corners: np.ndarray) -> float:
    top_left, top_right, _, _ = order_points(corners)
    return degrees(atan2(float(top_right[1] - top_left[1]), float(top_right[0] - top_left[0])))


def _candidate_score(extraction: Extraction, ocr_results: list[OcrResult], primary: bool) -> float:
    """Rank crops by how much of the document they actually read.

    Confidence alone is a trap here. A tight zoom on one corner of a card reads a few
    fragments with very high confidence, while the frame that contains the whole card reads
    every field at a slightly lower per-token score. Scoring confidence first therefore picks
    the fragment. Coverage of plausible characters and of distinct keys is weighted higher so
    the complete reading wins, and `plausible_line_ratio` still suppresses the case where a
    large crop is mostly background.
    """
    evidence = extraction.evidence
    plausible_ratio = float(evidence.get("plausible_line_ratio", 0.0))
    token_confidence = float(evidence.get("mean_token_confidence", 0.0))
    characters = float(evidence.get("plausible_characters", 0.0))
    if not extraction.fields:
        return -50.0
    if not characters and plausible_ratio < 0.4:
        return -40.0

    coverage = min(characters / 90.0, 3.0) * 55.0
    distinct_keys = len({item["name"] for item in extraction.fields})
    strong = [item for item in extraction.fields if item["confidence"] >= 0.6]
    return (
        coverage
        + distinct_keys * 14.0
        + len(strong) * 6.0
        + plausible_ratio * 18.0
        + token_confidence * 12.0
        + (3.0 if primary else 0.0)
    )


def _needs_alternatives(extraction: Extraction, ocr_results: list[OcrResult]) -> bool:
    if not extraction.fields:
        return True
    strong = [item for item in extraction.fields if item["confidence"] >= 0.62]
    if not strong:
        return True
    if float(extraction.evidence.get("plausible_line_ratio", 0.0)) < 0.5:
        return True
    return all(item["confidence"] < 0.8 for item in strong)


def process_image(
    input_path: Path,
    output_root: Path,
    job_id: str,
    options: ScanOptions,
    progress_callback: ProgressCallback | None = None,
) -> dict:
    started = time.perf_counter()
    image = read_image(input_path)
    height, width = image.shape[:2]
    image_area = float(width * height)
    job_output = output_root / job_id
    original_path = job_output / f"original{input_path.suffix.lower() or '.jpg'}"
    write_image(original_path, image)
    _notify(progress_callback, "ingest", 8, "Image loaded")
    detection = detect_document(image, options.document_type)
    assets = {
        "original": f"/outputs/{job_id}/{original_path.name}",
        "detected": f"/outputs/{job_id}/debug/document_detected.jpg",
    }
    if not detection.detected:
        detected_path = job_output / "debug" / "document_detected.jpg"
        write_image(detected_path, detection.debug_image)
        base_result = {
            "job_id": job_id,
            "document_detected": False,
            "rotation_angle": 0,
            "detection_area_ratio": 0,
            "detection_method": detection.method,
            "detection_score": detection.selection_score,
            "corners": [],
            "image_width": width,
            "image_height": height,
            "processing_time_ms": round((time.perf_counter() - started) * 1000, 2),
            "ocr_confidence": 0,
            # The same coverage keys are present on the failure path so the response schema
            # is uniform. A failed run extracted nothing, and saying so explicitly is the
            # point: it must never read as a partially successful parse.
            "extracted_field_count": 0,
            "recognised_field_count": 0,
            "extraction_coverage": 0,
            "detection_selection": "none",
            "fields": {
                "document_type": "undetermined",
                "classification": {
                    "document_type": "undetermined",
                    "score": 0,
                    "signals": [],
                },
                "fields": [],
            },
            "raw_text": "",
            "warnings": [],
            "assets": assets,
        }
        write_json(job_output / "metadata.json", base_result)
        _notify(progress_callback, "complete", 100, "No document detected")
        return base_result
    _notify(progress_callback, "detect", 24, "Document candidates analyzed")
    corners_list = [detection.corners, *detection.alternatives]
    methods = [detection.method, *detection.alternative_methods]
    evaluations: list[dict] = []

    def evaluate_candidate(index: int, candidate_corners: np.ndarray, method: str) -> dict:
        candidate_image = four_point_transform(image, candidate_corners)
        candidate_height, candidate_width = candidate_image.shape[:2]
        ocr_results = run_ocr_variants(candidate_image, options.ocr_language)
        extraction = parse_all(
            ocr_results, candidate_width, candidate_height, options.document_type
        )
        best_text = max(ocr_results, key=lambda item: len(item.text)) if ocr_results else None
        return {
            "corners": candidate_corners,
            "method": method,
            "corrected": candidate_image,
            "ocr_results": ocr_results,
            "extraction": extraction,
            "ocr": best_text,
            "score": _candidate_score(extraction, ocr_results, index == 0),
            "primary": index == 0,
        }

    candidate_items = list(zip(corners_list[:4], methods[:4], strict=False))
    # A small detected quad is often a logo or a fragment rather than the document, so the
    # untouched frame is offered as a candidate and the crop scorer decides. The trigger reads
    # only the first candidate: widening it to the largest available quad lets the full frame win
    # on coverage for cards whose document already fills the frame, because background lettering
    # is counted as recovered text. A clipped candidate is a detection problem, not something the
    # crop scorer should be asked to solve with a noisier alternative.
    primary_area = abs(cv2.contourArea(corners_list[0])) / image_area if corners_list else 0.0
    if primary_area < 0.5:
        candidate_items.append(
            (
                np.array(
                    [[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]],
                    dtype=np.int32,
                ),
                "full_frame_scan",
            )
        )
    last_index = len(candidate_items) - 1
    for index, (candidate_corners, method) in enumerate(candidate_items):
        evaluation = evaluate_candidate(index, candidate_corners, method)
        evaluations.append(evaluation)
        # Stop early only when nothing is left to try. Breaking out as soon as a candidate looks
        # adequate would skip the full-frame candidate appended above, and a card cropped to half
        # its width still parses a few fields well enough to look adequate.
        if index >= last_index:
            continue
        if (
            index == 0
            and primary_area >= 0.45
            and not _needs_alternatives(evaluation["extraction"], evaluation["ocr_results"])
        ):
            break
        # There is deliberately no "index > 0 and looks adequate" break here. That early exit
        # existed to save a recognition pass, but it also skipped the full-frame candidate
        # appended above, and a card cropped to half its width still parses a few fields well
        # enough to be called adequate. The only candidate holding the whole document was
        # therefore never compared against the clipped one.
    if evaluations and all(
        _needs_alternatives(evaluation["extraction"], evaluation["ocr_results"])
        for evaluation in evaluations
    ):
        full_frame = np.array(
            [[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]],
            dtype=np.int32,
        )
        evaluations.append(evaluate_candidate(len(evaluations), full_frame, "full_frame_fallback"))
    best_evaluation = max(evaluations, key=lambda item: float(item["score"]))
    if not best_evaluation["extraction"].fields and evaluations[0]["extraction"].fields:
        best_evaluation = evaluations[0]
    corners = np.asarray(best_evaluation["corners"], dtype=np.int32)
    corrected = np.asarray(best_evaluation["corrected"])
    method = str(best_evaluation["method"])
    extraction = best_evaluation["extraction"]
    ocr_result = best_evaluation["ocr"]
    area_ratio = abs(cv2.contourArea(corners)) / image_area
    rotation_angle = _rotation_angle(corners)
    debug_image = draw_detection_debug(image, corners, area_ratio, method, rotation_angle)
    write_image(job_output / "debug" / "document_detected.jpg", debug_image)
    corrected_path = job_output / "processed" / "corrected_document.jpg"
    write_image(corrected_path, corrected)
    assets["corrected"] = f"/outputs/{job_id}/processed/corrected_document.jpg"
    _notify(progress_callback, "correct", 46, "Perspective corrected")
    enhanced, enhancement_metadata = enhance_image(
        corrected,
        output_path=job_output / "processed" / "enhanced_document.jpg",
        cpp_acceleration=options.cpp_acceleration,
        fast_denoise=options.fast_denoise,
    )
    assets["enhanced"] = f"/outputs/{job_id}/processed/enhanced_document.jpg"
    _notify(progress_callback, "enhance", 66, "Document enhanced")
    _notify(progress_callback, "ocr", 86, "OCR and field parsing completed")
    warnings = [item for item in [ocr_result.warning] if item]
    raw_text = "\n".join(
        result.text for result in best_evaluation["ocr_results"] if result.text.strip()
    )
    token_confidences = [
        result.confidence for result in best_evaluation["ocr_results"] if result.confidence
    ]
    recognised = RECOGNISED_FIELDS.get(extraction.document_type, 0)
    extracted = len(extraction.fields)
    result = {
        "job_id": job_id,
        "document_detected": True,
        "rotation_angle": round(rotation_angle, 2),
        "detection_area_ratio": round(area_ratio, 4),
        "detection_method": method,
        "detection_score": detection.selection_score if best_evaluation["primary"] else 0,
        "detection_selection": "primary"
        if best_evaluation["primary"]
        else "ocr_validated_alternative",
        "corners": corners.tolist(),
        "image_width": width,
        "image_height": height,
        "processing_time_ms": round((time.perf_counter() - started) * 1000, 2),
        "ocr_confidence": round(max(token_confidences), 4) if token_confidences else 0,
        "field_confidence": summarise_confidence(extraction.fields),
        # Coverage is reported instead of a bare percentage so the UI cannot imply that a
        # confident OCR pass means a fully parsed document.
        "extracted_field_count": extracted,
        "recognised_field_count": recognised,
        "extraction_coverage": round(extracted / recognised, 4) if recognised else 0,
        "fields": {
            "document_type": extraction.document_type,
            "classification": extraction.classification,
            "fields": extraction.fields,
            "structured": extraction.structured,
            "unclassified": extraction.unclassified,
        },
        "raw_text": raw_text,
        "ocr": {
            "variants": len(best_evaluation["ocr_results"]),
            "selected": ocr_result.metadata.get("variant") if ocr_result else None,
            "evaluated_crops": len(evaluations),
            "evidence": extraction.evidence,
            "candidates": [
                {
                    "method": item["method"],
                    "score": round(float(item["score"]), 2),
                    "primary": item["primary"],
                    "area_ratio": round(
                        abs(cv2.contourArea(np.asarray(item["corners"]))) / image_area, 4
                    ),
                    "fields": len(item["extraction"].fields),
                    "strong_fields": sum(
                        1 for field in item["extraction"].fields if field["confidence"] >= 0.6
                    ),
                    "plausible_line_ratio": item["extraction"].evidence.get(
                        "plausible_line_ratio", 0.0
                    ),
                    "mean_token_confidence": item["extraction"].evidence.get(
                        "mean_token_confidence", 0.0
                    ),
                }
                for item in evaluations
            ],
        },
        "enhancement": enhancement_metadata,
        "warnings": warnings,
        "assets": assets,
    }
    write_json(job_output / "metadata.json", result)
    # The 100 refers to the run having finished, not to extraction quality. Spelling out the
    # recovered fraction stops a finished progress bar from reading as a fully parsed document.
    _notify(
        progress_callback,
        "complete",
        100,
        f"Processing complete, {extracted} of {recognised} recognised fields extracted",
    )
    return result
