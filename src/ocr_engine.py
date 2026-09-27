"""OCR built on PP-OCR through ONNX Runtime.

Why this engine
---------------
PP-OCR recognition is a convolutional model. Its error rate on printed business documents
is materially lower than a classical engine's, and the measured bottleneck in this project
was never the extraction rules but how much of the text the OCR step could read at all. It
also ships an angle classifier, which removes the need to hand-roll deskewing.

Detection granularity
---------------------
PP-OCR returns detected *text lines* with a polygon and one confidence per line, not
per-word tokens. That is the unit this module exposes. It is the right granularity for field
extraction, because printed fields are line shaped, and the layout model groups units into
columns and typographic tiers from exactly this information.

Language
--------
The bundled recognition model covers Latin and CJK scripts, which includes Indonesian,
English and Japanese. Tesseract's per-language traineddata selection is therefore gone;
`ocr_language` is retained on `ScanOptions` only so existing API and CLI callers keep
working, and it is reported back in the result metadata.
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from math import sqrt
from typing import Any

import cv2
import numpy as np

Image = np.ndarray
KEYWORDS = (
    "phone",
    "tel",
    "telp",
    "hp",
    "fax",
    "email",
    "e-mail",
    "total",
    "invoice",
    "date",
    "name",
    "nik",
    "address",
)

_ENGINE_LOCK = threading.Lock()
_ENGINE: Any = None
_ENGINE_FAILED: str | None = None


@dataclass(frozen=True)
class TextUnit:
    """One detected text line: its polygon, bounding box and recognition confidence."""

    text: str
    left: int
    top: int
    width: int
    height: int
    confidence: float
    index: int
    points: tuple[tuple[int, int], ...] = ()

    @property
    def char_height(self) -> float:
        return float(self.height)


@dataclass(frozen=True)
class OcrResult:
    text: str
    confidence: float
    lines: list[str] = field(default_factory=list)
    warning: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    words: list[TextUnit] = field(default_factory=list)


def engine_available() -> bool:
    """True when the OCR runtime can be constructed in this environment."""
    return get_engine() is not None


def engine_error() -> str | None:
    get_engine()
    return _ENGINE_FAILED


def get_engine() -> Any:
    """Construct the OCR engine once per process.

    The angle classifier is what makes a rotated or skewed capture readable without any
    custom deskew code, so it must stay enabled. RapidOCR 3.x exposes it as
    `Global.use_cls` and already defaults it to true; earlier releases took
    `use_angle_cls` as a direct keyword. Both are handled so the pinned major version can
    move without a code change.
    """
    global _ENGINE, _ENGINE_FAILED
    if _ENGINE is not None or _ENGINE_FAILED is not None:
        return _ENGINE
    with _ENGINE_LOCK:
        if _ENGINE is not None or _ENGINE_FAILED is not None:
            return _ENGINE
        try:
            from rapidocr import RapidOCR

            try:
                _ENGINE = RapidOCR(params={"Global.use_cls": True})
            except Exception:
                # rapidocr 1.x and 2.x took the switches as direct keywords. The ignore is
                # deliberate: if a future release accepts them again, the unused-ignore
                # warning tells us to drop this branch.
                _ENGINE = RapidOCR(  # type: ignore[call-arg]
                    use_angle_cls=True, use_text_det=True, use_text_rec=True
                )
        except Exception as error:  # pragma: no cover - depends on runtime packaging
            _ENGINE_FAILED = f"{type(error).__name__}: {error}"
            _ENGINE = None
    return _ENGINE


def _normalise_output(raw: Any) -> list[tuple[Any, str, float]]:
    """Normalise the engine's output across RapidOCR 1.x, 2.x and 3.x shapes."""
    if raw is None:
        return []
    payload = raw[0] if isinstance(raw, tuple) and len(raw) == 2 else raw
    if payload is None:
        return []
    boxes = getattr(payload, "boxes", None)
    texts = getattr(payload, "txts", None)
    scores = getattr(payload, "scores", None)
    if boxes is not None and texts is not None:
        pairs: list[tuple[Any, str, float]] = []
        for index, text in enumerate(texts):
            if index >= len(boxes):
                break
            score = float(scores[index]) if scores is not None and index < len(scores) else 0.0
            pairs.append((boxes[index], str(text), score))
        return pairs
    results: list[tuple[Any, str, float]] = []
    for item in payload if isinstance(payload, (list, tuple)) else []:
        try:
            box, value = item[0], item[1]
            text, score = value[0], value[1]
        except (IndexError, TypeError):
            continue
        results.append((box, str(text), float(score)))
    return results


def _unit_from(box: Any, text: str, score: float, index: int) -> TextUnit | None:
    cleaned = " ".join(str(text).split())
    if not cleaned:
        return None
    points: tuple[tuple[int, int], ...] = ()
    if box is not None:
        try:
            points = tuple((int(point[0]), int(point[1])) for point in box)
        except (TypeError, ValueError):
            points = ()
    if points:
        left = min(point[0] for point in points)
        top = min(point[1] for point in points)
        right = max(point[0] for point in points)
        bottom = max(point[1] for point in points)
    else:
        left, top, right, bottom = 0, 0, len(cleaned) * 8, 18
    width = max(right - left, 1)
    height = max(bottom - top, 1)
    return TextUnit(cleaned, left, top, width, height, score, index, points)


def _token_score(token: str, confidence: float) -> float:
    alphanumeric = sum(character.isalnum() for character in token)
    if alphanumeric < 2:
        return -4.0
    quality = confidence / 100 * sqrt(alphanumeric)
    if "@" in token:
        quality += 20
    if any(keyword in token.casefold() for keyword in KEYWORDS):
        quality += 4
    if alphanumeric / max(len(token), 1) < 0.55:
        quality -= 6
    return quality


def _is_low_information(result: OcrResult) -> bool:
    words = re.findall(r"[A-Za-z0-9@]+", result.text)
    if not words:
        return True
    has_signal = "@" in result.text or any(
        keyword in result.text.casefold() for keyword in KEYWORDS
    )
    return result.confidence < 0.45 and not has_signal and len(words) < 12


def _upscale(image: Image, scale: float) -> Image:
    if scale == 1.0:
        return image
    return cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)


def _variants(image: Image) -> list[tuple[str, Image]]:
    """Image-level variants. PP-OCR has no page-segmentation mode, so diversity comes from
    the input image rather than from OCR parameters."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    small = max(gray.shape[:2])
    base = _upscale(gray, 3.0 if small < 800 else 1.5) if small < 3200 else gray

    denoised = cv2.bilateralFilter(cv2.medianBlur(base, 3), 5, 25, 25)
    clahe = cv2.createCLAHE(clipLimit=2.2, tileGridSize=(10, 10)).apply(denoised)
    blurred = cv2.GaussianBlur(clahe, (0, 0), 1.0)
    sharpened = cv2.addWeighted(blurred, 1.5, clahe, -0.5, 0)

    block = max(31, min(101, (min(sharpened.shape) // 3) * 2 + 1))
    adaptive = cv2.adaptiveThreshold(
        sharpened, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, block, 13
    )
    adaptive = cv2.morphologyEx(adaptive, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))

    background = cv2.GaussianBlur(base, (0, 0), sigmaX=28, sigmaY=28)
    shadow = cv2.divide(base, background, scale=255)
    shadow = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(shadow)

    return [
        ("as_is", base),
        ("clahe_sharp", sharpened),
        ("adaptive", adaptive),
        ("shadow_normalized", shadow),
    ]


def looks_blank(image: Image) -> bool:
    """Conservative pre-check for a genuinely empty surface.

    A clean high-contrast document also has low edge density, so a loose threshold would
    silently refuse to read every well-lit scan. Only a nearly uniform surface qualifies;
    everything else is handed to the engine, which decides emptiness from what it read.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    if float(np.std(gray)) >= 8.0:
        return False
    edges = cv2.Canny(cv2.GaussianBlur(gray, (3, 3), 0), 50, 150)
    return float(np.count_nonzero(edges)) / float(edges.size) < 0.004


def _run_variant(image: Image, variant: str) -> OcrResult | None:
    engine = get_engine()
    if engine is None:
        return None
    try:
        raw = engine(image)
    except Exception:
        return None
    pairs = _normalise_output(raw)
    units: list[TextUnit] = []
    for index, (box, text, score) in enumerate(pairs):
        unit = _unit_from(box, text, score, index)
        if unit is not None:
            units.append(unit)
    if not units:
        return None
    units.sort(key=lambda unit: (unit.top, unit.left))
    texts = [unit.text for unit in units]
    score = 0.0
    for unit in units:
        for token in unit.text.split():
            score += _token_score(token, unit.confidence * 100)
    confidence = sum(unit.confidence for unit in units) / len(units)
    return OcrResult(
        "\n".join(texts),
        round(confidence, 4),
        texts,
        None,
        {"variant": variant, "engine": "ppocr", "selection_score": round(score, 2)},
        units,
    )


def run_ocr_variants(image: Image, languages: str = "eng+ind") -> list[OcrResult]:
    """Run every image variant and return all readings.

    The parser votes across these rather than trusting one winner, because the best reading
    of one field is frequently not in the best overall reading.
    """
    if get_engine() is None:
        return [
            OcrResult(
                "",
                0,
                [],
                f"OCR engine unavailable ({_ENGINE_FAILED})",
                {"variant": "engine_unavailable"},
            )
        ]
    if looks_blank(image):
        return [
            OcrResult(
                "",
                0,
                [],
                "No visible text detected on the document",
                {"variant": "blank", "engine": "ppocr"},
            )
        ]
    results: list[OcrResult] = []
    for name, variant_image in _variants(image):
        candidate = _run_variant(variant_image, name)
        if candidate is not None:
            results.append(candidate)
    if not results:
        return [
            OcrResult(
                "",
                0,
                [],
                "OCR engine returned no result",
                {"variant": "failed", "engine": "ppocr", "candidates": 0},
            )
        ]
    return results


def run_ocr(image: Image, languages: str = "eng+ind") -> OcrResult:
    """Return the single best-scoring variant, for callers that need one result."""
    results = run_ocr_variants(image, languages)
    if not results:
        return OcrResult("", 0, [], "OCR engine returned no result", {"variant": "failed"})
    if results[0].metadata.get("variant") in {"blank", "engine_unavailable", "failed"}:
        return results[0]
    best = max(results, key=lambda item: float(item.metadata["selection_score"]))
    if _is_low_information(best):
        return OcrResult(
            "",
            best.confidence,
            [],
            "OCR found no reliable text",
            {**best.metadata, "variant": "low_information", "candidates": len(results)},
            best.words,
        )
    return OcrResult(
        best.text,
        best.confidence,
        best.lines,
        best.warning,
        {
            **best.metadata,
            "candidates": len(results),
            "requested_language": languages,
            "tesseract_available": False,
        },
        best.words,
    )
