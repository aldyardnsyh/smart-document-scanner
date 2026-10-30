"""Bundle pipeline outputs into static frontend fixtures.

Reads ``outputs/demo/<slug>/<job>/metadata.json``, copies the four image assets into
``frontend/public/demo/<slug>/`` at display size, rewrites the asset URLs so the browser can
serve them, and emits ``frontend/src/lib/demo-fixtures.json`` as a ``Job[]`` that matches
``frontend/src/lib/types.ts``.

The demo must never reach into ``outputs/`` at runtime: the folder is not shipped with the
static build, and any leftover ``/outputs/`` path would 404 in the browser.
"""

from __future__ import annotations

import glob
import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs" / "demo"
PUBLIC_DEMO = ROOT / "frontend" / "public" / "demo"
FIXTURES_PATH = ROOT / "frontend" / "src" / "lib" / "demo-fixtures.json"
NO_DOCUMENT_SRC = ROOT / "dataset" / "no_document.jpg"

MAX_EDGE = 1400
JPEG_QUALITY = 78
ASSET_KEYS = ("original", "detected", "corrected", "enhanced")
# types.ts types `unclassified[].tier` as a number, while the OCR report emits a tier name.
TIER_RANK = {"primary": 1, "secondary": 2, "tertiary": 3, "body": 4}

# One entry per demo job. ``slug`` doubles as the output folder name and the public URL
# segment; ``job_id`` is the frontend-facing id and must match ``result.job_id``.
SEEDS = [
    {
        "id": "seed-01",
        "slug": "business_card",
        "original_name": "avery-lindgren-card.jpg",
        "created_at": "2026-10-24T09:12:00Z",
    },
    {
        "id": "seed-02",
        "slug": "receipt",
        "original_name": "harbor-cafe-receipt.jpg",
        "created_at": "2026-10-25T13:41:00Z",
    },
    {
        "id": "seed-03",
        "slug": "id_card",
        "original_name": "ktp-budi-santoso.jpg",
        "created_at": "2026-10-26T08:05:00Z",
    },
    {
        "id": "seed-04",
        "slug": "paper_document",
        "original_name": "mou-northline-harbor.jpg",
        "created_at": "2026-10-27T16:22:00Z",
    },
    {
        "id": "seed-05",
        "slug": "no_document",
        "original_name": "blank-desk-photo.jpg",
        "created_at": "2026-10-27T10:03:00Z",
        "failed": True,
    },
    {
        "id": "seed-06",
        "slug": "blank",
        "original_name": "blank-card.jpg",
        "created_at": "2026-10-28T11:47:00Z",
    },
]

SUCCESS_MESSAGE = "Processing complete."
FAILED_MESSAGE = "No document contour was found in this image."


def find_metadata(slug: str) -> Path:
    """Resolve the single metadata file for a demo slug, ignoring folder name drift."""
    matches = sorted(glob.glob(str(OUTPUTS / slug / "*" / "metadata.json")))
    if len(matches) != 1:
        raise SystemExit(f"expected exactly one metadata.json under {OUTPUTS / slug}, got {matches}")
    return Path(matches[0])


def resolve_asset(reference: str, job_dir: Path) -> Path:
    """Map a stored ``/outputs/<job>/...`` reference back onto the local job folder."""
    parts = [part for part in Path(reference.replace("\\", "/")).parts if part not in ("/", "\\")]
    if parts and parts[0] == "outputs":
        parts = parts[1:]
    if parts and parts[0] == job_dir.name:
        parts = parts[1:]
    candidate = job_dir.joinpath(*parts)
    if not candidate.is_file():
        raise SystemExit(f"asset referenced in metadata does not exist: {reference} -> {candidate}")
    return candidate


def export_image(source: Path, target: Path) -> None:
    """Copy an asset as a bounded JPEG so the demo stays light on the wire."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as image:
        rgb = image.convert("RGB")
        rgb.thumbnail((MAX_EDGE, MAX_EDGE), Image.LANCZOS)
        rgb.save(target, format="JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)


def copy_assets(metadata: dict, job_dir: Path, slug: str) -> None:
    assets = metadata.get("assets") or {}
    for key in ASSET_KEYS:
        reference = assets.get(key)
        if not reference:
            raise SystemExit(f"{job_dir.name}: metadata has no '{key}' asset")
        export_image(resolve_asset(reference, job_dir), PUBLIC_DEMO / slug / f"{key}.jpg")


def normalise_ocr(ocr: dict | None) -> dict | None:
    """Collapse the pipeline's OCR report onto the subset declared in types.ts."""
    if not isinstance(ocr, dict):
        return None
    return {
        "variant": ocr.get("selected") or ocr.get("variant") or "unknown",
        "evaluated_crops": int(ocr.get("evaluated_crops") or 0),
        "candidates": len(ocr.get("candidates") or []),
    }


def normalise_unclassified(entries: list) -> list:
    """Convert tier names to the numeric rank types.ts expects, dropping unusable values."""
    cleaned = []
    for entry in entries:
        item = dict(entry)
        tier = item.get("tier")
        if isinstance(tier, str):
            rank = TIER_RANK.get(tier.lower())
            if rank is None:
                item.pop("tier", None)
            else:
                item["tier"] = rank
        elif tier is not None and not isinstance(tier, int):
            item.pop("tier", None)
        cleaned.append(item)
    return cleaned


def normalise_result(metadata: dict, job_id: str, slug: str) -> dict:
    """Return a ScanResult whose keys line up with types.ts and whose assets are public URLs."""
    result = json.loads(json.dumps(metadata))
    # types.ts declares no field_confidence on ScanResult, so it must not leak into fixtures.
    result.pop("field_confidence", None)
    result["job_id"] = job_id
    result["assets"] = {key: f"/demo/{slug}/{key}.jpg" for key in ASSET_KEYS}
    fields = result.get("fields")
    if isinstance(fields, dict) and isinstance(fields.get("unclassified"), list):
        fields["unclassified"] = normalise_unclassified(fields["unclassified"])
    if "ocr" in result:
        normalised = normalise_ocr(result.get("ocr"))
        if normalised is None:
            result.pop("ocr")
        else:
            result["ocr"] = normalised
    return result


def failed_result(job_id: str) -> dict:
    """A completed-but-empty scan: the upload had no document contour to find."""
    return {
        "job_id": job_id,
        "document_detected": False,
        "rotation_angle": 0.0,
        "detection_area_ratio": 0.0,
        "detection_method": "none",
        "detection_score": 0.0,
        "detection_selection": "none",
        "corners": [],
        "image_width": 0,
        "image_height": 0,
        "processing_time_ms": 0,
        "ocr_confidence": 0.0,
        "extracted_field_count": 0,
        "recognised_field_count": 0,
        "extraction_coverage": 0.0,
        "fields": {
            "document_type": "auto",
            "classification": {"document_type": "auto", "score": 0.0, "signals": []},
            "fields": [],
            "unclassified": [],
        },
        "raw_text": "",
        "warnings": [FAILED_MESSAGE],
        "assets": {
            "original": "/demo/no_document/original.jpg",
            "detected": "/demo/no_document/original.jpg",
        },
    }


def build_job(seed: dict) -> dict:
    job_id = seed["id"]
    slug = seed["slug"]
    if seed.get("failed"):
        return {
            "id": job_id,
            "original_name": seed["original_name"],
            "status": "failed",
            "stage": "failed",
            "progress": 100,
            "message": FAILED_MESSAGE,
            "created_at": seed["created_at"],
            "updated_at": seed["created_at"],
            "result": failed_result(job_id),
            "error": {"code": "no_document", "message": FAILED_MESSAGE},
        }

    metadata_path = find_metadata(slug)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    copy_assets(metadata, metadata_path.parent, slug)
    return {
        "id": job_id,
        "original_name": seed["original_name"],
        "status": "completed",
        "stage": "parse",
        "progress": 100,
        "message": SUCCESS_MESSAGE,
        "created_at": seed["created_at"],
        "updated_at": seed["created_at"],
        "result": normalise_result(metadata, job_id, slug),
        "error": None,
    }


def directory_size(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def human_size(size: int) -> str:
    if size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.2f} MB"
    return f"{size / 1024:.1f} KB"


def main() -> int:
    if not NO_DOCUMENT_SRC.is_file():
        raise SystemExit(f"missing source image: {NO_DOCUMENT_SRC}")
    PUBLIC_DEMO.mkdir(parents=True, exist_ok=True)
    export_image(NO_DOCUMENT_SRC, PUBLIC_DEMO / "no_document" / "original.jpg")

    jobs = [build_job(seed) for seed in SEEDS]

    FIXTURES_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(jobs, indent=2, ensure_ascii=False) + "\n"
    if "/outputs/" in payload:
        raise SystemExit("refusing to write fixtures: a /outputs/ path leaked into the JSON")
    FIXTURES_PATH.write_text(payload, encoding="utf-8")

    total_assets = directory_size(PUBLIC_DEMO)
    print(f"fixtures: {FIXTURES_PATH}")
    print(f"assets:   {PUBLIC_DEMO} ({human_size(total_assets)})")
    print(f"json:     {human_size(FIXTURES_PATH.stat().st_size)}")
    for job in jobs:
        result = job["result"] or {}
        fields = result.get("fields") or {}
        print(
            "  {id} | {doc:<15} | fields={count:<2} | {status}".format(
                id=job["id"],
                doc=fields.get("document_type", "-"),
                count=len(fields.get("fields") or []),
                status=job["status"],
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())