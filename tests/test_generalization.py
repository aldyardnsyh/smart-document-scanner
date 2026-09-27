"""Held-out vocabulary fixtures.

None of these strings appear in `dataset` or in the curated ground truth.
They exist to prove the parser generalises: recognition must come from printed labels,
value shapes and layout, never from memorised answers.

These are intentionally text-level cases so the assertion is fast and deterministic; the
image-based check lives in the manual hold-out run described in the README.
"""

from __future__ import annotations

import pytest

from src.field_parser import _looks_like_person_name, _match_label, parse_fields
from src.ocr_engine import OcrResult

HELD_OUT_CARDS: list[dict[str, str]] = [
    {
        "name": "Budi Santoso",
        "company": "PT ARTA BANGUN PERKASA",
        "title": "Manajer Operasional",
        "address": "Jl. Merdeka No. 45, Bandung 40115",
        "email": "budi.santoso@artabangun.co.id",
        "phone": "022-87654321",
    },
    {
        "name": "Hiroshi Tanaka",
        "company": "TANAKA ELECTRIC CO., LTD.",
        "title": "Sales Manager",
        "address": "3-1-1 Marunouchi, Chiyoda-ku, Tokyo 100-0005",
        "email": "h.tanaka@tanaka-elec.co.jp",
        "phone": "+81-3-5555-1234",
    },
    {
        "name": "Andi Prasetyo",
        "company": "NUSANTARA JAYA TRANSPORT",
        "title": "Head of Operations",
        "address": "Jl. Veterans No. 12, Semarang 50134",
        "email": "andi.prasetyo@nusantarajaya.co.id",
        "phone": "024-7654321",
    },
]

# Text layout the OCR engine would produce for each held-out card.
HELD_OUT_TEXTS: list[str] = [
    "\n".join(
        [
            "PT ARTA BANGUN PERKASA",
            "Budi Santoso",
            "Manajer Operasional",
            "Jl. Merdeka No. 45, Bandung 40115",
            "Telp: 022-87654321",
            "budi.santoso@artabangun.co.id",
        ]
    ),
    "\n".join(
        [
            "TANAKA ELECTRIC CO., LTD.",
            "Hiroshi Tanaka",
            "Sales Manager",
            "3-1-1 Marunouchi, Chiyoda-ku, Tokyo 100-0005",
            "Tel: +81-3-5555-1234",
            "h.tanaka@tanaka-elec.co.jp",
        ]
    ),
    "\n".join(
        [
            "NUSANTARA JAYA TRANSPORT",
            "Andi Prasetyo",
            "Head of Operations",
            "Jl. Veterans No. 12, Semarang 50134",
            "Tel: 024-7654321",
            "andi.prasetyo@nusantarajaya.co.id",
        ]
    ),
]


@pytest.mark.parametrize("text", HELD_OUT_TEXTS)
def test_held_out_cards_yield_their_contact_details(text: str) -> None:
    """Email and telephone must be recovered from printed labels on unseen wording."""
    parsed = parse_fields(text, "business_card", 1000, 600)
    lookup = {item["name"]: item["value"] for item in parsed["fields"]}
    assert "@" in lookup.get("email", "")
    assert any(character.isdigit() for character in lookup.get("phone", ""))


@pytest.mark.parametrize("card", HELD_OUT_CARDS)
def test_held_out_person_names_are_recognised(card: dict[str, str]) -> None:
    assert _looks_like_person_name(card["name"]), card["name"]


@pytest.mark.parametrize(
    ("line", "expected_key"),
    [
        ("Telp: 022-87654321", "phone"),
        ("Tel: +81-3-5555-1234", "phone"),
        ("NAMA: Budi Santoso", "name"),
        ("Email: andi@example.co.id", "email"),
    ],
)
def test_printed_labels_are_recognised_independently_of_the_dataset(
    line: str, expected_key: str
) -> None:
    matched = _match_label(line)
    assert matched is not None, line
    assert matched[0] == expected_key


def test_legal_forms_select_the_company_key() -> None:
    parsed = parse_fields(HELD_OUT_TEXTS[0], "business_card", 1000, 600)
    sources = {item["source"] for item in parsed["fields"]}
    assert any("organization" in source or "unit" in source for source in sources)


def test_unreadable_input_yields_no_confident_fields() -> None:
    garbage = OcrResult("~ ~ ~ ~ ~ ~ ~", 0.2, ["~ ~ ~"], None, {"variant": "x"}, [])
    assert parse_fields(garbage.text, "business_card", 500, 300)["fields"] == []
