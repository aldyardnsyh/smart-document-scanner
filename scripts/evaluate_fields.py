"""Score extracted fields against the curated ground truth in tests/fixtures/valid_extraction.json.

Usage:
    python scripts/evaluate_fields.py <batch_summary.json> [--json] [--min-score 0.95]

Scoring is per ground-truth key so that document-specific schemas are respected:
a card that legitimately has no fax is not penalised, but a wrong fax is.
"""

from __future__ import annotations

import argparse
import json
import re
import string
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
GROUND_TRUTH_PATH = ROOT_DIR / "tests" / "fixtures" / "valid_extraction.json"
PUNCTUATION = str.maketrans("", "", string.punctuation)


def normalize(value: Any) -> str:
    text = str(value).casefold()
    text = text.translate(PUNCTUATION)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def token_set(value: Any) -> list[str]:
    return [token for token in normalize(value).split() if token]


def similarity(expected: Any, actual: Any) -> float:
    """Graded 0..1 match. Exact match is required for full credit."""
    if expected is None or actual is None:
        return 0.0
    expected_text = normalize(expected)
    actual_text = normalize(actual)
    if not expected_text:
        return 1.0 if not actual_text else 0.0
    if expected_text == actual_text:
        return 1.0
    expected_tokens = token_set(expected)
    actual_tokens = token_set(actual)
    if not expected_tokens or not actual_tokens:
        return 0.0
    # Numeric-only comparisons ignore separators: 1.650.725.7076 == 16507257076
    expected_digits = re.sub(r"\D", "", expected_text)
    actual_digits = re.sub(r"\D", "", actual_text)
    if expected_digits and actual_digits and expected_digits == actual_digits:
        return 1.0
    if expected_digits and actual_digits and not token_set(expected_text):
        if expected_digits in actual_digits or actual_digits in expected_digits:
            return 0.9
    expected_pool = list(expected_tokens)
    matched = 0
    for token in actual_tokens:
        if token in expected_pool:
            expected_pool.remove(token)
            matched += 1
            continue
        for candidate in list(expected_pool):
            if (
                len(token) > 3
                and len(candidate) > 3
                and (token.startswith(candidate[:4]) or candidate.startswith(token[:4]))
            ):
                expected_pool.remove(candidate)
                matched += 1
                break
    recall = matched / len(expected_tokens)
    precision = matched / len(actual_tokens)
    if recall + precision == 0:
        return 0.0
    f1 = 2 * recall * precision / (recall + precision)
    if f1 >= 0.9:
        return 0.85
    if f1 >= 0.7:
        return 0.6
    if f1 >= 0.45:
        return 0.3
    return 0.0


def flatten(payload: Any, prefix: str = "") -> dict[str, Any]:
    """Flatten nested structures into dotted paths.

    A list of {"name": ..., "value": ...} objects collapses to the name as the key so
    that the flat field list and a nested dict score identically.
    """
    flat: dict[str, Any] = {}
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in {"document_type", "classification", "unclassified", "evidence"}:
                continue
            path = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(value, (dict, list)) and key not in {"value"}:
                child = flatten(value, path)
                if child:
                    flat.update(child)
                elif not isinstance(value, list):
                    flat[path] = value
            else:
                flat[path] = value
    elif isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict) and "name" in item and "value" in item:
                key = f"{prefix}.{item['name']}" if prefix else str(item["name"])
                flat[key] = item["value"]
            elif isinstance(item, dict):
                flat.update(flatten(item, prefix))
    return flat


def record_fields(payload: dict[str, Any]) -> dict[str, Any]:
    """Map one pipeline record's fields envelope to flat ground-truth style keys.

    The envelope is {"document_type", "classification", "fields": [name/value rows],
    "structured": {...}}. Flat rows land at the root so that a card's `address`
    matches the ground truth key `address`, and nested structures keep dotted paths.
    """
    flat: dict[str, Any] = {}
    for item in payload.get("fields", []) or []:
        if isinstance(item, dict) and "name" in item:
            flat[str(item["name"])] = item.get("value")
    structured = payload.get("structured") or {}
    if isinstance(structured, dict):
        for key, value in structured.items():
            if isinstance(value, dict):
                for sub_key, sub_value in value.items():
                    flat[f"{key}.{sub_key}"] = sub_value
            else:
                flat[key] = value
    return flat


def score_document(expected: dict[str, Any], actual_flat: dict[str, Any]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for key, expected_value in expected.items():
        actual_value = actual_flat.get(key)
        rows.append(
            {
                "key": key,
                "expected": expected_value,
                "actual": actual_value,
                "score": similarity(expected_value, actual_value),
                "status": "exact"
                if similarity(expected_value, actual_value) == 1.0
                else ("partial" if actual_value is not None else "missing"),
            }
        )
    expected_keys = set(expected)
    false_positives = sorted(key for key in actual_flat if key not in expected_keys)
    return {
        "rows": rows,
        "false_positives": false_positives,
        "mean": sum(row["score"] for row in rows) / len(rows) if rows else 0.0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("summary", type=Path, help="batch_summary.json produced by app.py")
    parser.add_argument("--json", action="store_true", help="emit machine-readable output")
    parser.add_argument("--min-score", type=float, default=0.95)
    parser.add_argument("--verbose", action="store_true", help="print every key row")
    arguments = parser.parse_args()

    if not arguments.summary.exists():
        print(f"summary not found: {arguments.summary}", file=sys.stderr)
        return 2

    ground_truth = json.loads(GROUND_TRUTH_PATH.read_text(encoding="utf-8"))
    records = json.loads(arguments.summary.read_text(encoding="utf-8"))
    by_stem = {re.sub(r"^cli-\d+-", "", str(record["job_id"])): record for record in records}

    if arguments.json:
        payload = {}
        for stem, expected in ground_truth.items():
            record = by_stem.get(stem)
            if record is None:
                payload[stem] = {"error": "missing from summary", "mean": 0.0}
                continue
            actual_flat = record_fields(record.get("fields", {}))
            payload[stem] = score_document(expected, actual_flat)
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    total_score = 0.0
    total_keys = 0
    exact_keys = 0
    missing_keys = 0
    total_false_positives = 0
    per_file: list[tuple[str, float, int, int, int, int]] = []
    failures: list[str] = []

    header = f"{'file':<22} {'mean':>6} {'keys':>5} {'exact':>6} {'miss':>5} {'fp':>4}"
    print(header)
    print("-" * len(header))

    for stem, expected in sorted(ground_truth.items()):
        record = by_stem.get(stem)
        if record is None:
            print(f"{stem:<22} {'ABSENT':>6}")
            failures.append(f"{stem}: absent from summary")
            total_keys += len(expected)
            continue
        actual_flat = record_fields(record.get("fields", {}))
        result = score_document(expected, actual_flat)
        keys = len(result["rows"])
        exact = sum(1 for row in result["rows"] if row["status"] == "exact")
        missing = sum(1 for row in result["rows"] if row["status"] == "missing")
        false_positives = len(result["false_positives"])
        total_score += result["mean"] * keys
        total_keys += keys
        exact_keys += exact
        missing_keys += missing
        total_false_positives += false_positives
        per_file.append((stem, result["mean"], keys, exact, missing, false_positives))
        if result["mean"] < arguments.min_score:
            failures.append(f"{stem}: {result['mean']:.3f}")
        if arguments.verbose:
            for row in result["rows"]:
                flag = {"exact": "OK  ", "partial": "PART", "missing": "MISS"}[row["status"]]
                print(
                    f"    {flag} {row['key']:<22} {row['score']:.2f} "
                    f"expected={row['expected']!r} actual={row['actual']!r}"
                )
            if result["false_positives"]:
                print(f"    EXTRA keys not in ground truth: {result['false_positives']}")
        cells = (stem, f"{result['mean']:>6.3f}", keys, exact, missing, false_positives)
        print(f"{cells[0]:<22} {cells[1]} {cells[2]:>5} {cells[3]:>6} {cells[4]:>5} {cells[5]:>4}")

    mean_score = total_score / total_keys if total_keys else 0.0
    exact_rate = exact_keys / total_keys if total_keys else 0.0
    total_cells = ("OVERALL", f"{mean_score:>6.3f}", total_keys, exact_keys, missing_keys)
    print("-" * len(header))
    print(
        f"{total_cells[0]:<22} {total_cells[1]} {total_cells[2]:>5} "
        f"{total_cells[3]:>6} {total_cells[4]:>5} {total_false_positives:>4}"
    )
    print()
    target = arguments.min_score * 100
    print(f"mean per-key score : {mean_score * 100:.1f}%   (target >= {target:.0f}%)")
    print(f"exact-match rate   : {exact_rate * 100:.1f}%")
    print(f"keys missing       : {missing_keys}/{total_keys}")
    print(f"unsupported extras : {total_false_positives}")
    if failures:
        print("below target: " + ", ".join(failures))
    return 0 if mean_score >= arguments.min_score else 1


if __name__ == "__main__":
    raise SystemExit(main())
