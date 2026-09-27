import re
from dataclasses import dataclass
from typing import Any

NIK_PATTERN = re.compile(r"\b\d{16}\b")
ID_MARKERS = (
    "nik",
    "date of birth",
    "birth date",
    "tanggal lahir",
    "tempat/tgl lahir",
    "jenis kelamin",
    "gol. darah",
    "golongan darah",
    "blood type",
    "rt/rw",
    "kel/desa",
    "kecamatan",
    "status perkawinan",
    "kewarganegaraan",
)
RECEIPT_MARKERS = (
    "receipt",
    "invoic",
    "total",
    "subtotal",
    "tax",
    "tax rate",
    "amount due",
    "bill to",
    "billed to",
    "due date",
    "change",
)
PAPER_MARKERS = (
    "stock debit note",
    "document",
    "report",
    "statement",
    "item code",
    "description",
    "qty",
)
BUSINESS_MARKERS = ("phone", "tel", "fax", "e-mail", "email", "mobile", "website", "company")


@dataclass(frozen=True)
class ClassificationResult:
    document_type: str
    score: float
    signals: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_type": self.document_type,
            "score": self.score,
            "signals": self.signals,
        }


def _matched_markers(text: str, markers: tuple[str, ...]) -> list[str]:
    """Word-boundary marker match.

    Substring matching misfires badly here: "tel" matches inside "telp" and "hotel",
    "total" inside "totally", and a single stray word can tip the whole classification.
    """
    hits: list[str] = []
    for marker in markers:
        pattern = rf"(?<![a-z0-9]){re.escape(marker.casefold())}(?![a-z0-9])"
        if re.search(pattern, text):
            hits.append(marker)
    return hits


def classify_document(
    text: str,
    width: int,
    height: int,
    requested_type: str = "auto",
) -> ClassificationResult:
    if requested_type != "auto":
        return ClassificationResult(requested_type, 100.0, ["manual_override"])
    lowered = text.casefold()
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    aspect_ratio = width / max(height, 1)
    scores = {
        "business_card": 0.0,
        "id_card": 0.0,
        "receipt": 0.0,
        "paper_document": 0.0,
    }
    signals: dict[str, list[str]] = {key: [] for key in scores}
    if NIK_PATTERN.search(text):
        scores["id_card"] += 8
        signals["id_card"].append("16_digit_nik")
    for marker in _matched_markers(lowered, ID_MARKERS):
        scores["id_card"] += 1.5
        signals["id_card"].append(marker)
    for marker in _matched_markers(lowered, RECEIPT_MARKERS):
        scores["receipt"] += 1.8
        signals["receipt"].append(marker)
    for marker in _matched_markers(lowered, PAPER_MARKERS):
        scores["paper_document"] += 1.7
        signals["paper_document"].append(marker)
    for marker in _matched_markers(lowered, BUSINESS_MARKERS):
        scores["business_card"] += 1.6
        signals["business_card"].append(marker)
    if "@" in text:
        scores["business_card"] += 4
        signals["business_card"].append("email_address")
    if re.search(r"\b(?:phone|tel|fax)\b", lowered):
        scores["business_card"] += 2.5
        signals["business_card"].append("labeled_phone")
    if 1.25 <= aspect_ratio <= 2.8 and len(lines) <= 40:
        scores["business_card"] += 2.2
        scores["id_card"] += 0.6
        signals["business_card"].append("landscape_card_aspect")
    if len(lines) >= 22:
        scores["paper_document"] += 2.5
        signals["paper_document"].append("dense_text_layout")
    if aspect_ratio < 0.95 and len(lines) >= 8:
        scores["receipt"] += 1.2
        scores["paper_document"] += 0.8
        signals["receipt"].append("portrait_layout")
    if "invoic" in lowered:
        scores["receipt"] += 5
        signals["receipt"].append("invoice_label")
    if not text.strip():
        if aspect_ratio >= 1.25:
            scores["business_card"] += 3
            signals["business_card"].append("blank_landscape_card")
        else:
            scores["paper_document"] += 2
            signals["paper_document"].append("blank_no_text")
    document_type = max(scores, key=lambda key: scores[key])
    total = sum(scores.values())
    score = round(scores[document_type] / total * 100, 1) if total else 0.0
    return ClassificationResult(document_type, score, signals[document_type])
