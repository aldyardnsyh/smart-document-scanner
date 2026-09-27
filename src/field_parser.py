"""Layout-aware, evidence-tiered field extraction with cross-variant voting.

Design rules that this module must not break:

1. No dataset vocabulary. Nothing here may contain a word that only appears in the test
   photographs. Recognition comes from printed labels (a document convention that
   generalises), value shapes (regex), and layout geometry.
2. No fabricated confidence. Every confidence is computed from measured evidence:
   how many independent OCR variants agree, the engine's own token confidence, and
   which tier of evidence produced the value.
3. No silent guessing. Text that no rule can explain is returned in `unclassified`
   rather than being assigned to a plausible-looking key.
"""

from __future__ import annotations

import math
import re
import statistics
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any

from .classifier import classify_document
from .layout import Layout, LineBlock, build_layout
from .ocr_engine import OcrResult

# --------------------------------------------------------------------------------------
# Value shapes (tier 1). Language independent.
# --------------------------------------------------------------------------------------

EMAIL_PATTERN = re.compile(r"[A-Z0-9._%+-]+\s*@\s*[A-Z0-9.-]+\s*\.\s*[A-Z]{2,6}", re.IGNORECASE)
URL_PATTERN = re.compile(r"\b(?:https?://|www\.)[A-Z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+", re.IGNORECASE)
NIK_PATTERN = re.compile(r"\b\d{16}\b")
LONG_DIGIT_RUN = re.compile(r"(?:\+\d|\d)[\d\s().+-]{7,}\d")
DATE_PATTERNS = (
    re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-](?:\d{2}|\d{4})\b"),
    re.compile(r"\b\d{4}[/-]\d{1,2}[/-]\d{1,2}\b"),
    re.compile(
        r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[\s-]\d{1,2}[\s-]\d{2,4}\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b\d{1,2}[\s-](?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[\s-]\d{2,4}\b",
        re.IGNORECASE,
    ),
)
MONEY_PATTERN = re.compile(r"[$€£]\s?\d[\d.,]*|\b\d[\d.,]*\s?(?:USD|EUR|IDR|Rp)\b", re.IGNORECASE)
PERCENT_PATTERN = re.compile(r"\b\d+(?:[.,]\d+)?\s?%")

# --------------------------------------------------------------------------------------
# Printed label lexicon (tier 2). These are document conventions, not dataset trivia.
# Keys map to the canonical field name emitted in the output.
# --------------------------------------------------------------------------------------

CARD_LABELS: dict[str, tuple[str, ...]] = {
    "name": ("name", "nama", "full name", "nama lengkap", "contact name", "person"),
    "title": (
        "title",
        "jabatan",
        "posisi",
        "designation",
        "role",
        "position",
        "job title",
        "fungsi",
    ),
    "organization": ("organization", "organisasi", "org", "institution", "institusi"),
    "company": ("company", "perusahaan", "firm", "corporation", "nama perusahaan"),
    "department": (
        "department",
        "departemen",
        "dept",
        "division",
        "divisi",
        "unit",
        "laboratory",
        "laboratorium",
        "lab",
        "group",
        "kelompok",
    ),
    "email": ("email", "e-mail", "mail", "surel", "email address"),
    "phone": (
        "phone",
        "tel",
        "telp",
        "telephone",
        "hp",
        "mobile",
        "handphone",
        "no tel",
        "nomor",
        "phone number",
        "telno",
    ),
    "fax": ("fax", "efaks"),
    "website": ("website", "web", "url", "site", "www", "homepage"),
    "address": ("address", "alamat", "lokasi", "location", "office"),
}

KTP_LABELS: dict[str, tuple[str, ...]] = {
    "provinsi": ("provinsi", "province", "propinsi"),
    "kabupaten": ("kabupaten", "kab."),
    "kota": ("kota", "city"),
    "nik": ("nik", "no nik", "nomor nik", "national id"),
    "nama": ("nama", "name", "nama lengkap"),
    "tempat_tgl_lahir": (
        "tempat tgl lahir",
        "tempat/tgl lahir",
        "tempat dan tanggal lahir",
        "tgl lahir",
        "tanggal lahir",
        "place of birth",
        "birth place",
        "date of birth",
        "birth date",
        "birthdate",
        "dob",
        "ttl",
    ),
    "jenis_kelamin": ("jenis kelamin", "j.k", "jk", "gender", "sex"),
    "gol_darah": ("golongan darah", "gol darah", "blood type", "gol. darah"),
    "alamat": ("alamat", "address"),
    "rt_rw": ("rt/rw", "rt rw", "rt-rw"),
    "kel_desa": ("kel/desa", "kel desa", "kelurahan", "desa", "village"),
    "kecamatan": ("kecamatan", "kec", "district", "sub district"),
    "agama": ("agama", "religion"),
    "status_perkawinan": ("status perkawinan", "status核对", "marital status", "status tinggal"),
    "pekerjaan": ("pekerjaan", "occupation", "profession", "job"),
    "kewarganegaraan": ("kewarganegaraan", "citizenship", "nationality"),
    "berlaku_hingga": ("berlaku hingga", "berlaku sampai", "valid until", "valid till"),
}

RECEIPT_LABELS: dict[str, tuple[str, ...]] = {
    "title": ("invoice", "invoice #", "receipt", "bill", "statement", "quotation"),
    "ref_number": ("ref", "ref no", "reference", "reference number", "no", "number", "inv no"),
    "date": ("date", "invoice date", "tanggal", "issued"),
    "due_date": ("due date", "due", "payment due", "jatuh tempo"),
    "subtotal": ("subtotal", "sub total", "sub-total"),
    "tax": ("tax", "ppn", "vat", "sales tax"),
    "tax_rate": ("tax rate", "ppn", "vat %"),
    "discount": ("discount", "diskon", "disc"),
    "total": ("total", "grand total", "amount due", "jumlah", "bayar", "total due"),
    "billed_from": ("billed from", "from", "seller", "supplier", "vendor"),
    "billed_to": ("billed to", "bill to", "to", "customer", "client"),
    "footer": ("footer",),
}

PAPER_LABELS: dict[str, tuple[str, ...]] = {
    "document_type": ("document type", "jenis dokumen"),
    "vendor_name": ("vendor name", "vendor", "supplier"),
    "vendor_ntn": ("vendor ntn", "ntn"),
    "voucher_no": ("voucher no", "voucher", "no voucher"),
    "voucher_date": ("voucher date", "tanggal"),
    "inv_no": ("inv no", "invoice no"),
    "company_code": ("company code", "kode perusahaan"),
    "page_info": ("page", "halaman"),
    "prepared_by": ("prepared by", "dibuat oleh"),
    "it_incharge": ("it incharge", "it in charge"),
    "branch_manager": ("branch manager", "manajer cabang"),
    "auditor": ("auditor", "audit"),
}

ALL_LABELS: dict[str, tuple[str, ...]] = {}
for _table in (CARD_LABELS, KTP_LABELS, RECEIPT_LABELS, PAPER_LABELS):
    for _key, _aliases in _table.items():
        ALL_LABELS.setdefault(_key, ())
        ALL_LABELS[_key] = ALL_LABELS[_key] + _aliases

# --------------------------------------------------------------------------------------
# Structural morphology (tier 3/4). Generic domain vocabulary only.
# --------------------------------------------------------------------------------------

LEGAL_FORMS = (
    "ltd",
    "limited",
    "inc",
    "incorporated",
    "llc",
    "plc",
    "corp",
    "corporation",
    "gmbh",
    "nv",
    "bv",
    "pty",
    "pte",
    "sdn",
    "bhd",
    "tbk",
    "pt",
    "cv",
    "kk",
    "company",
    "co",
)

INSTITUTION_WORDS = (
    "university",
    "universitas",
    "institute",
    "institut",
    "forum",
    "association",
    "foundation",
    "college",
    "school",
    "academy",
    "hospital",
    "library",
    "museum",
    "society",
    "council",
    "committee",
    "center",
    "centre",
    "laboratory",
    "laboratorium",
)

DEPARTMENT_WORDS = (
    "department",
    "departemen",
    "dept",
    "division",
    "divisi",
    "unit",
    "faculty",
    "group",
    "team",
    "section",
    "office of",
    "laboratory",
    "laboratorium",
    "lab",
)

JOB_TITLES = (
    "engineer",
    "manager",
    "director",
    "officer",
    "president",
    "consultant",
    "scientist",
    "specialist",
    "analyst",
    "designer",
    "developer",
    "professor",
    "researcher",
    "scholar",
    "architect",
    "technician",
    "supervisor",
    "coordinator",
    "assistant",
    "librarian",
    "attendant",
    "staff",
    "intern",
    "lecturer",
    "instructor",
    "auditor",
    "accountant",
    "dentist",
)

STREET_WORDS = (
    "street",
    "st.",
    "road",
    "rd.",
    "avenue",
    "ave.",
    "jalan",
    "jl.",
    "raya",
    "boulevard",
    "blvd",
    "drive",
    "lane",
    "court",
    "circle",
    "plaza",
    "mall",
    "building",
    "bldg",
    "floor",
    "suite",
    "komplek",
    "complex",
    "tower",
    "gang",
    "gg.",
    "perkantoran",
)

REGION_WORDS = (
    "jawa",
    "sumatera",
    "kalimantan",
    "sulawesi",
    "papua",
    "bali",
    "lombok",
    "ca",
    "ny",
    "tx",
    "oh",
    "japan",
    "indonesia",
    "uk",
    "germany",
    "france",
    "usa",
    "state",
    "province",
    "city",
)

# Words that must never be treated as a personal name.
ACADEMIC_WORDS = (
    "engineering",
    "science",
    "sciences",
    "arts",
    "humanities",
    "medicine",
    "law",
    "economics",
    "commerce",
    "computing",
    "mathematics",
    "statistics",
    "physics",
    "chemistry",
    "biology",
    "accounting",
    "marketing",
    "management",
    "informatics",
)

NON_NAME_MARKERS = (
    LEGAL_FORMS
    + INSTITUTION_WORDS
    + DEPARTMENT_WORDS
    + JOB_TITLES
    + STREET_WORDS
    + REGION_WORDS
    # A field of study reads exactly like a person name to a purely typographic check: two
    # capitalised words, no digits. Without this list, a department line is reported as the
    # cardholder's name and the real name is lost.
    + ACADEMIC_WORDS
    + ("inc.", "ltd.", "univ", "univ.", "tel", "phone", "fax", "email", "e-mail", "www")
)

TIER_WEIGHT = {1: 1.0, 2: 0.9, 3: 0.72, 4: 0.55}


@dataclass(frozen=True)
class Candidate:
    name: str
    value: str
    tier: int
    source: str
    token_confidence: float
    layout: Layout | None = None
    line: LineBlock | None = None

    @property
    def weight(self) -> float:
        return TIER_WEIGHT.get(self.tier, 0.4) * max(self.token_confidence, 0.05)


@dataclass
class Extraction:
    fields: list[dict[str, Any]] = field(default_factory=list)
    structured: dict[str, Any] = field(default_factory=dict)
    unclassified: list[dict[str, Any]] = field(default_factory=list)
    document_type: str = "undetermined"
    classification: dict[str, Any] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" \t[](){}<>|,;:")


def _key_of(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def _numeric_key(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    letters = re.sub(r"[^a-z]+", "", value.casefold())
    return f"{digits}|{letters}"


# --------------------------------------------------------------------------------------
# Tier 1: value shapes
# --------------------------------------------------------------------------------------


def _repair_email(value: str) -> str:
    compact = re.sub(r"\s+", "", value)
    if "@" not in compact:
        return compact
    local, _, domain = compact.partition("@")
    if "." not in domain:
        parts = [part for part in re.split(r"[^A-Za-z]+", value.split("@", 1)[1]) if part]
        if len(parts) >= 2:
            domain = f"{parts[0]}.{''.join(parts[1:])}"
    return f"{local}@{domain}".rstrip(".,;:")


def _tier1_from_text(text: str, confidence: float) -> list[Candidate]:
    found: list[Candidate] = []
    for name, pattern in (("email", EMAIL_PATTERN), ("website", URL_PATTERN)):
        for match in pattern.finditer(text):
            value = _normalize(match.group(0))
            value = _repair_email(value) if name == "email" else value.replace(" ", "")
            if _acceptable(value):
                found.append(Candidate(name, value, 1, f"{name}_shape", confidence))
    for match in NIK_PATTERN.finditer(text):
        found.append(Candidate("nik", match.group(0), 1, "nik_shape", confidence))
    for pattern in DATE_PATTERNS:
        for match in pattern.finditer(text):
            found.append(Candidate("date", match.group(0).strip(), 1, "date_shape", confidence))
    for match in MONEY_PATTERN.finditer(text):
        value = _normalize(match.group(0))
        if re.search(r"\d", value):
            found.append(Candidate("money", value, 1, "money_shape", confidence))
    for match in PERCENT_PATTERN.finditer(text):
        found.append(
            Candidate("percent", _normalize(match.group(0)), 1, "percent_shape", confidence)
        )
    for match in LONG_DIGIT_RUN.finditer(text):
        value = _normalize(match.group(0))
        if len(re.sub(r"\D", "", value)) >= 7 and not NIK_PATTERN.fullmatch(value.strip()):
            found.append(Candidate("phone_like", value, 1, "digit_run_shape", confidence))
    return found


# --------------------------------------------------------------------------------------
# Tier 2: printed label anchors
# --------------------------------------------------------------------------------------

_ANCHOR_PAIRS: list[tuple[str, str]] = sorted(
    ((key, alias) for key, aliases in ALL_LABELS.items() for alias in aliases),
    key=lambda item: -len(item[1]),
)
_ANCHOR_INDEX: list[tuple[str, tuple[str, ...]]] = []
for _key, _alias in _ANCHOR_PAIRS:
    for _position, (_existing_key, _existing_aliases) in enumerate(_ANCHOR_INDEX):
        if _existing_key == _key:
            _ANCHOR_INDEX[_position] = (_existing_key, (*_existing_aliases, _alias))
            break
    else:
        _ANCHOR_INDEX.append((_key, (_alias,)))


def _match_label(line_text: str) -> tuple[str, str] | None:
    """Return (canonical_key, remainder) when a line starts with a known printed label."""
    stripped = line_text.strip()
    if not stripped:
        return None
    body = re.sub(r"^[^A-Za-z0-9]+", "", stripped)
    lowered = body.casefold()
    for key, aliases in _ANCHOR_INDEX:
        for alias in aliases:
            alias_low = alias.casefold()
            if lowered == alias_low:
                return key, ""
            for separator in (":", "-", "="):
                prefix = f"{alias_low}{separator}"
                if lowered.startswith(prefix):
                    remainder = body[len(alias) + len(separator) :].strip(" :.-")
                    return key, remainder
            if lowered.startswith(f"{alias_low} "):
                remainder = body[len(alias) :].strip(" :.-")
                if remainder:
                    return key, remainder
    return None


def _tier2_from_layout(layout: Layout, confidence_scale: float) -> list[Candidate]:
    candidates: list[Candidate] = []
    for line in layout.lines:
        matched = _match_label(line.text)
        if matched is None:
            continue
        key, remainder = matched
        if not remainder:
            continue
        remainder = _truncate_at_next_label(remainder, key)
        remainder = _strip_debris(remainder, key)
        if not _acceptable(remainder):
            continue
        if key == "email":
            remainder = _repair_email(remainder)
        if key == "website":
            remainder = remainder.replace(" ", "")
        token_confidence = max(min(line.confidence / 100, 1.0), 0.05) * confidence_scale
        candidates.append(
            Candidate(key, _normalize(remainder), 2, f"label:{key}", token_confidence, layout, line)
        )
    return candidates


def _trailing_head_noun(text: str, markers: tuple[str, ...]) -> bool:
    """True when the marker sits at the end of the line, as in `SALES FORUM`."""
    tokens = re.findall(r"[A-Za-z0-9]+", text)
    if not tokens:
        return False
    tail = " ".join(tokens[-2:]).casefold()
    return any(marker.casefold() in tail for marker in markers)


def _mergeable(key: str) -> tuple[str, ...]:
    """Keys whose value frequently wraps onto the following printed line."""
    if key == "address":
        return ("address", "company", "organization", "institution", "laboratory", "department")
    if key in {"organization", "company", "department", "institution", "laboratory"}:
        return ("address",)
    return ()


_TIER_RANK = {"primary": 3, "secondary": 2, "body": 1, "tertiary": 0}


def _is_upper_style(text: str) -> bool:
    letters = [character for character in text if character.isalpha()]
    if len(letters) < 3:
        return False
    return sum(1 for character in letters if character.isupper()) / len(letters) >= 0.85


_NOISE_TOKEN = re.compile(r"^[^A-Za-z0-9]+$|^\d+$")


def _strip_line_noise(text: str) -> str:
    """Drop isolated junk tokens from the edges of a line.

    Noisy captures make the OCR engine glue debris onto a real line, such as a stray digit
    in front of the content and a pipe character after it. Trimming the edges lets the real
    content be matched instead of being rejected along with its neighbours.
    """
    tokens = text.split()
    start = 0
    end = len(tokens)
    while start < end and _NOISE_TOKEN.match(tokens[start]):
        start += 1
    while end > start and _NOISE_TOKEN.match(tokens[end - 1]):
        end -= 1
    return " ".join(tokens[start:end])


def _name_spans(text: str, maximum: int = 4) -> list[str]:
    """Every maximal run of consecutive tokens that reads like a personal name.

    A person's name is not identifiable from a whole printed line, because a noisy capture
    merges the name with whatever surrounds it, for example a stray digit in front of it and
    a logo word behind it. Searching spans inside the line is what makes the name recoverable
    without knowing the card's wording.
    """
    tokens = _strip_line_noise(text).split()
    spans: list[str] = []
    for size in range(min(maximum, len(tokens)), 1, -1):
        for start in range(0, len(tokens) - size + 1):
            window = tokens[start : start + size]
            if _looks_like_person_name(" ".join(window)):
                spans.append(" ".join(window))
    return spans


def _is_plausible_phone(value: str) -> bool:
    digits = re.sub(r"\D", "", value)
    if len(digits) < 7:
        return False
    for pattern in DATE_PATTERNS:
        if pattern.fullmatch(value.strip()):
            return False
    return True


def _label_residual_block(text: str) -> tuple[str | None, bool]:
    """Name a leftover block from its own content.

    The returned flag says whether the name was inferred from morphology rather than read
    from a printed label. Nothing here is keyed to a particular dataset: it reuses the same
    generic lexicons the typed pass uses, and returns ``None`` when none of them apply, so
    the caller can say "unlabelled" rather than invent a name.
    """
    has_digit = bool(re.search(r"\d", text))
    if _has_marker(text, STREET_WORDS) and has_digit:
        return "address", True
    if _has_marker(text, REGION_WORDS) and has_digit:
        return "address", True
    if _is_address_continuation(text):
        return "address", True
    if _has_marker(text, DEPARTMENT_WORDS) and len(text.split()) <= 10:
        role = _organization_role(text)
        return (role if role in {"department", "laboratory", "institution"} else "department"), True
    if _has_marker(text, LEGAL_FORMS + INSTITUTION_WORDS) and len(text.split()) <= 10:
        return _organization_role(text), True
    if _has_marker(text, JOB_TITLES) and len(text.split()) <= 6:
        return "title", True
    return None, True


def _group_residual(lines: list[LineBlock]) -> list[dict[str, Any]]:
    """Group unclaimed lines into blocks by column and vertical adjacency.

    Grouping is purely geometric. A printed address, a department name, or an organisation
    head noun all arrive as consecutive lines in the same column, and grouping them the same
    way keeps the decision independent of what the words happen to be.
    """
    if not lines:
        return []
    ordered = sorted(lines, key=lambda line: (line.column, line.top))
    blocks: list[list[LineBlock]] = []
    current: list[LineBlock] = [ordered[0]]
    current_label, _ = _label_residual_block(ordered[0].text)
    for line in ordered[1:]:
        previous = current[-1]
        same_column = line.column == previous.column
        # A gap larger than roughly one line height means the eye would read something else
        # in between, so it starts a new block.
        touching = 0 <= line.top - (previous.top + previous.height) <= previous.height * 1.4
        line_label, _ = _label_residual_block(line.text)
        # Only lines that read as the same kind of thing may share a block. Grouping purely by
        # adjacency merged a department line into a postal address, because the block was then
        # named from its combined text and the street word won.
        homogeneous = line_label == current_label
        if same_column and touching and homogeneous:
            current.append(line)
        else:
            blocks.append(current)
            current = [line]
            current_label = line_label
    blocks.append(current)

    result: list[dict[str, Any]] = []
    for block in blocks:
        text = ", ".join(line.text.strip() for line in block).strip()
        if not text:
            continue
        label, inferred = _label_residual_block(text)
        # Confidence stays at the lowest line in the block and is capped, because a name we
        # inferred ourselves is weaker evidence than a printed label.
        confidence = min(line.confidence for line in block) / 100
        if inferred:
            confidence = min(confidence, 0.55)
        result.append(
            {
                "value": text,
                "label": label,
                "inferred": inferred,
                "confidence": round(confidence, 3),
                "tier": min(line.tier for line in block),
                "lines": [line.text for line in block],
                "anchor": block[0],
            }
        )
    return result


def _recover_from_residual(
    fields: list[dict[str, Any]], pool: list[Candidate], layout: Any
) -> None:
    """Fold leftover blocks back into typed fields where the fit is structural.

    Two cases are safe to act on, and both are decided by layout rather than vocabulary:

    * a leftover block that continues an existing address, which the typed pass had to stop
      because an unrelated line sat between the printed lines;
    * a leftover block sitting directly above an organisation line, which is the common
      case of a name whose head noun wrapped onto the next line.

    Everything else is left in ``unclassified`` for the caller to see rather than guessed at.
    """
    residual = [item for item in pool if item.source == "residual_block"]
    if not residual:
        return
    for block in residual:
        label = block.name
        if label != "address":
            continue
        address = next((item for item in fields if item["name"] == "address"), None)
        if address is None:
            continue
        if block.value.casefold() in str(address["value"]).casefold():
            continue
        if not _is_address_continuation(block.value) and not _has_marker(block.value, STREET_WORDS):
            continue
        joined = f"{address['value']}, {block.value}" if address["value"] else block.value
        if len(joined) <= 130:
            address["value"] = joined
            address["confidence"] = min(
                float(address.get("confidence", 0.5)), 0.62, block.token_confidence
            )
            address.setdefault("source", "")
            address["source"] = f"{address['source']}+residual_address".strip("+")


def _is_address_continuation(text: str) -> bool:
    """True when an unclassified line plausibly continues a postal address.

    A postal address is routinely printed over several lines, and the continuation lines
    rarely repeat a street or region keyword, so morphology alone cannot recognise them. It
    is judged on structure instead: it must not introduce a different kind of field, and it
    must not look like a person's name, which would mean the column has moved on to the
    name block.
    """
    stripped = text.strip()
    if not stripped or not is_plausible_text(stripped):
        return False
    if _looks_like_person_name(stripped):
        return False
    # A continuation cannot introduce its own contact channel, and cannot start with a
    # printed label, because that label belongs to a different field.
    if EMAIL_PATTERN.search(stripped) or URL_PATTERN.search(stripped):
        return False
    if LONG_DIGIT_RUN.search(stripped) and not re.search(r"\d{3,}[-\s]?\d{3,}", stripped):
        return False
    if _match_label(stripped) is not None:
        return False
    # Trailing separators mean the print continued onto the next line.
    region_tokens = {word.lower() for word in re.findall(r"[A-Za-z]+", stripped)}
    return stripped.endswith((",", "-", "/", ":")) or bool(
        re.search(
            r"(?i)\b(?:ca|ny|tx|wa|ma|il|pa|oh|mi|mn|or|co|ut|va|md|dc|uk|jp|de|fr)\b",
            stripped,
        )
        or re.search(r"\b\d{5}(?:-\d{4})?\b", stripped)
        or bool(set(REGION_WORDS) & region_tokens)
    )


def _line_confidence(line: LineBlock, confidence_scale: float) -> float:
    return max(min(line.confidence / 100, 1.0), 0.05) * confidence_scale


def _tier34_from_layout(layout: Layout, confidence_scale: float) -> list[Candidate]:
    candidates: list[Candidate] = []
    if not layout.lines:
        return candidates
    anchored_lines = {id(line) for line in layout.lines if _match_label(line.text) is not None}
    bodies = [line for line in layout.lines if id(line) not in anchored_lines]

    def classify_line(line: LineBlock) -> tuple[str | None, str, tuple[str, ...]]:
        if not is_plausible_text(line.text):
            return None, "", ()
        if _has_marker(line.text, STREET_WORDS) and re.search(r"\d", line.text):
            return "address", "street_morphology", STREET_WORDS
        if _has_marker(line.text, JOB_TITLES) and len(line.text.split()) <= 6:
            return "title", "job_title_morphology", JOB_TITLES
        if _has_marker(line.text, DEPARTMENT_WORDS) and len(line.text.split()) <= 10:
            role = _organization_role(line.text)
            return (
                role if role in {"department", "laboratory", "institution"} else "department",
                "unit_morphology",
                DEPARTMENT_WORDS,
            )
        if _has_marker(line.text, LEGAL_FORMS + INSTITUTION_WORDS) and len(line.text.split()) <= 10:
            return _organization_role(line.text), "organization_morphology", INSTITUTION_WORDS
        if _has_marker(line.text, REGION_WORDS) and re.search(r"\d", line.text):
            return "address", "region_morphology", REGION_WORDS
        return None, "", ()

    # Pass 1: give every line its own key from morphology alone.
    decisions: list[tuple[str | None, str, tuple[str, ...]]] = []
    for line in bodies:
        decisions.append(classify_line(line))

    # Pass 2: collapse runs of the same key *within a column*. A card commonly prints an
    # organisation block on the left and contact details on the right, so a global top-to-
    # bottom order interleaves the two columns and the two halves of one organisation name
    # end up separated. A postal address legitimately spans several printed lines, but a
    # name and an organisation are separate fields and must never be joined.
    column_groups: dict[int, list[int]] = {}
    for position, line in enumerate(bodies):
        column_groups.setdefault(line.column, []).append(position)

    merged_values: dict[int, str] = {}
    for positions in column_groups.values():
        for offset, position in enumerate(positions):
            key = decisions[position][0]
            if key is None:
                continue
            line = bodies[position]
            parts = [line.text]
            for follower in positions[offset + 1 :]:
                next_key = decisions[follower][0]
                candidate_line = bodies[follower]
                if not _mergeable(key):
                    break
                if next_key == key:
                    pass
                elif (
                    key == "address"
                    and next_key is None
                    and _is_address_continuation(candidate_line.text)
                ):
                    # Absorb an unclassified line into the address. Stopping here is what
                    # truncated every multi-line address to its first line.
                    pass
                else:
                    break
                if _looks_like_person_name(candidate_line.text):
                    break
                if len(" ".join(parts)) + len(candidate_line.text) > 130:
                    break
                parts.append(candidate_line.text)
            merged_values[position] = ", ".join(parts)

    for position, line in enumerate(bodies):
        key, source, _ = decisions[position]
        if key is None:
            continue
        value = merged_values.get(position, line.text)
        token_confidence = _line_confidence(line, confidence_scale)
        candidates.append(Candidate(key, value, 3, source, token_confidence, layout, line))

    # An all-caps line directly above an all-caps organisation line in the same column is
    # usually the same name split by OCR, for example a body name wrapping onto its head noun.
    org_family = {"organization", "laboratory", "institution", "department"}
    previous_in_column: dict[int, int] = {}
    for positions in column_groups.values():
        for above, below in zip(positions, positions[1:], strict=False):
            previous_in_column[below] = above

    for position, line in enumerate(bodies):
        key, source, _ = decisions[position]
        if key not in org_family:
            continue
        neighbour = previous_in_column.get(position)
        if neighbour is None:
            continue
        previous = bodies[neighbour]
        if decisions[neighbour][0] is not None or not _is_upper_style(previous.text):
            continue
        if not _is_upper_style(line.text) or _looks_like_person_name(previous.text):
            continue
        for index, candidate in enumerate(candidates):
            if candidate.line is line and candidate.value == merged_values.get(position):
                candidates[index] = Candidate(
                    key,
                    f"{previous.text} {candidate.value}",
                    3,
                    f"{source}+wrapped_name",
                    _line_confidence(previous, confidence_scale),
                    layout,
                    line,
                )
                break

    # Tier 4: the person name is the most prominent readable name span on the card.
    org_lines = {
        id(line)
        for line, (key, _, _) in zip(bodies, decisions, strict=True)
        if key in {"organization", "company", "department", "institution", "laboratory"}
    }
    name_candidates: list[tuple[int, float, float, str]] = []
    for line in bodies:
        if id(line) in org_lines:
            # A name-looking fragment inside a line that already reads as an organisation is
            # part of that organisation, not a person.
            continue
        for span in _name_spans(line.text):
            name_candidates.append(
                (
                    _TIER_RANK.get(line.tier, 0),
                    line.char_height,
                    line.confidence,
                    span,
                )
            )
    if name_candidates:
        _rank, _height, line_confidence_value, span = max(
            name_candidates, key=lambda item: item[:3]
        )
        token_confidence = max(min(line_confidence_value / 100, 1.0), 0.05) * confidence_scale
        span_line = next(
            (line for line in bodies if span in _strip_line_noise(line.text)),
            bodies[0],
        )
        candidates.append(
            Candidate(
                "name",
                span,
                4,
                "typographic_prominence",
                token_confidence,
                layout,
                span_line,
            )
        )
    return candidates


# --------------------------------------------------------------------------------------
# Tier 3/4: morphology and typography
# --------------------------------------------------------------------------------------


def _has_marker(text: str, markers: tuple[str, ...]) -> bool:
    """Word-boundary marker match.

    Substring matching is unsafe here: "co" would match "company" and "cost", "pt"
    would match "department", and short garbage tokens would match almost anything.
    """
    tokens = set(re.findall(r"[a-z0-9]+", text.casefold()))
    padded = f" {text.casefold()} "
    for marker in markers:
        parts = [part for part in re.split(r"[^a-z0-9]+", marker.casefold()) if part]
        if not parts:
            continue
        if len(parts) == 1:
            if parts[0] in tokens:
                return True
            if f" {marker.casefold()} " in padded:
                return True
            continue
        joined = " ".join(parts)
        if joined in padded:
            return True
    return False


NOISE_CHARACTERS = set("|~=+*_`^<>{}[]\\/@#$%&")
_ALLOWED_NOISE_PUNCTUATION = set(".,:;-'\"()")


def _acceptable(value: str) -> bool:
    """Lenient check for tier 1 and tier 2, which are precise by construction.

    A regex match or a printed label anchor is trustworthy even when the value has no
    letters at all (`009/014`) or is a single character (blood type `O`).
    """
    stripped = value.strip()
    if not stripped:
        return False
    return sum(1 for character in stripped if character in NOISE_CHARACTERS) <= 1


def value_quality(value: str) -> float:
    """Fraction of characters that look like real text.

    Used to rank competing candidates for the same key, never to hard-reject a value,
    because legitimate fields include all-digit and single-character content.
    """
    stripped = value.strip()
    if not stripped:
        return 0.0
    good = sum(
        1
        for character in stripped
        if character.isalnum() or character.isspace() or character in _ALLOWED_NOISE_PUNCTUATION
    )
    return round(good / len(stripped), 3)


def is_plausible_text(value: str, minimum: float = 0.6) -> bool:
    """Reject OCR noise for the guessy tiers, which infer a key from morphology alone."""
    stripped = value.strip()
    if len(stripped) < 2:
        return False
    if sum(1 for character in stripped if character.isalpha()) < 2:
        return False
    if sum(1 for character in stripped if character in NOISE_CHARACTERS) > 1:
        return False
    return value_quality(stripped) >= minimum


def _truncate_at_next_label(text: str, own_key: str) -> str:
    """Cut a label remainder where the next printed label begins.

    ID cards print `LABEL value LABEL value` on one physical line, so the naive remainder
    swallows the following field's value. The repeat case (a label echoed twice by OCR)
    keeps its full value instead of being cut to nothing.
    """
    own_aliases = set(ALL_LABELS.get(own_key, ()))
    stripped = text.strip()
    for alias in own_aliases:
        if stripped.casefold().startswith(f"{alias.casefold()} "):
            return stripped
    best_cut = len(text)
    for _key, aliases in _ANCHOR_INDEX:
        for alias in aliases:
            for separator in (":", "-", "="):
                needle = f" {alias.casefold()}{separator}"
                position = text.casefold().find(needle)
                if position != -1:
                    best_cut = min(best_cut, position)
            needle = f" {alias.casefold()} "
            position = text.casefold().find(needle)
            if position != -1 and position > 0:
                best_cut = min(best_cut, position)
    candidate = text[:best_cut].strip(" ,;:-")
    return candidate if len(candidate) >= 2 else text.strip(" ,;:-")


_TRAILING_DEBRIS = re.compile(
    r"\s+(?:ma|mb|a|b|c|d|e|f|di|dan|dan|yang|the|of|no|on|at|in)\s*$",
    re.IGNORECASE,
)


def _strip_debris(value: str, own_key: str) -> str:
    """Remove single-character OCR debris that trails a short form value.

    Card and ID-card layouts put two fields on one text line, so a value often ends with
    the first letter of whatever followed it, for example `009/014 Ma`. Values with real
    multi-word content are left alone.
    """
    stripped = value.strip()
    if len(stripped.split()) > 6:
        return stripped
    for _ in range(3):
        cleaned = _TRAILING_DEBRIS.sub("", stripped).strip()
        if cleaned == stripped or not cleaned:
            break
        stripped = cleaned
    if own_key in {"gol_darah", "jenis_kelamin", "agama"} and len(stripped) <= 3:
        return stripped
    return stripped


def _organization_role(text: str) -> str:
    tokens = set(re.findall(r"[a-z0-9]+", text.casefold()))
    for form in LEGAL_FORMS:
        if form in tokens:
            return "company"
    if _has_marker(text, ("laboratory", "laboratorium", "lab")):
        return "laboratory"
    if _has_marker(text, ("library", "museum", "hospital")):
        return "institution"
    if _has_marker(text, DEPARTMENT_WORDS):
        return "department"
    if _has_marker(text, INSTITUTION_WORDS):
        return "organization"
    return "organization"


def _looks_like_person_name(text: str) -> bool:
    tokens = text.split()
    if not 2 <= len(tokens) <= 5:
        return False
    if any(character.isdigit() for character in text) or "@" in text or "." in text:
        return False
    if _has_marker(text, NON_NAME_MARKERS):
        return False
    if not all(any(character.isalpha() for character in token) for token in tokens):
        return False
    if not all(token[:1].isupper() for token in tokens):
        return False
    return True


# --------------------------------------------------------------------------------------
# Cross-variant voting
# --------------------------------------------------------------------------------------


LENGTH_SENSITIVE_KEYS = {
    "address",
    "organization",
    "company",
    "department",
    "institution",
    "laboratory",
}


def _token_subset(smaller: str, larger: str) -> bool:
    small_tokens = [token for token in _key_of(smaller).split() if token]
    large_tokens = set(_key_of(larger).split())
    return bool(small_tokens) and all(token in large_tokens for token in small_tokens)


def _prefer_complete_values(
    winners: list[dict[str, Any]], pool: list[Candidate]
) -> list[dict[str, Any]]:
    """Prefer the more complete value for keys where length carries meaning.

    A three-line postal address is recognised intact in only some variants, while the
    truncated first line appears in most. Plain support counting therefore prefers the
    incomplete value. When a longer candidate for the same key contains every token of the
    winner and has comparable support, the longer one is taken.
    """
    by_key: dict[str, list[Candidate]] = {}
    for candidate in pool:
        if candidate.name in LENGTH_SENSITIVE_KEYS:
            by_key.setdefault(candidate.name, []).append(candidate)

    adjusted: list[dict[str, Any]] = []
    for item in winners:
        key = item["name"]
        if key not in LENGTH_SENSITIVE_KEYS:
            adjusted.append(item)
            continue
        current = str(item["value"])
        current_support = int(item.get("evidence", {}).get("support", 1))
        best_value = current
        best_confidence = float(item["confidence"])
        for candidate in by_key.get(key, []):
            if candidate.value == current or not is_plausible_text(candidate.value):
                continue
            if not _token_subset(current, candidate.value):
                continue
            if len(candidate.value) <= len(best_value):
                continue
            support = sum(
                1 for other in by_key[key] if _key_of(other.value) == _key_of(candidate.value)
            )
            if support < max(1, math.ceil(current_support * 0.5)):
                continue
            best_value = candidate.value
            best_confidence = max(best_confidence, min(0.95, candidate.weight * 1.15))
        if best_value == current:
            adjusted.append(item)
        else:
            adjusted.append(
                {
                    **item,
                    "value": _normalize(best_value),
                    "confidence": round(best_confidence, 3),
                    "source": f"{item['source']}+completed",
                }
            )
    return adjusted


DIGIT_REQUIRED_KEYS = {"nik", "rt_rw", "gol_darah", "no_hp"}
DATE_KEYS = {"date", "tempat_tgl_lahir", "voucher_date", "due_date", "birth_date"}
LABEL_PREFIXED_KEYS = {"provinsi": "PROVINSI", "kabupaten": "KABUPATEN", "kota": "KOTA"}


def _enforce_key_shape(key: str, value: str) -> str | None:
    """Reject or trim a value that cannot be right for its key.

    A `nik` that is not mostly digits is a mis-read, and a non-date key that has swallowed
    a full date has absorbed the neighbouring printed field.
    """
    text = _normalize(value)
    if key in DIGIT_REQUIRED_KEYS:
        digits = re.sub(r"\D", "", text)
        if not digits:
            return None
        if key == "nik" and len(digits) < 12:
            return None
        if key == "gol_darah" and not re.fullmatch(r"[A-Za-z]{1,4}", text):
            return None
    if key not in DATE_KEYS:
        cut = re.search(r"\s+\d{1,2}[/-]\d{1,2}[/-](?:\d{2}|\d{4})\s*$", text)
        if cut:
            text = text[: cut.start()].strip(" ,;:-")
    prefix = LABEL_PREFIXED_KEYS.get(key)
    if prefix and not text.casefold().startswith(prefix.casefold()):
        text = f"{prefix} {text}"
    if key == "gol_darah":
        match = re.search(r"\b([A-Za-z]{1,4})\b", text)
        text = match.group(1) if match else ""
    text = text.strip(".,;:-!| ")
    if key in {"phone", "fax", "tel"} and not _is_plausible_phone(text):
        return None
    return text or None


def _document_heading(layout: Layout | None, fields: list[dict[str, Any]]) -> str | None:
    """The line a form or note uses to name itself: prominent, unclaimed, mostly letters."""
    if layout is None:
        return None
    claimed = {str(item["value"]).casefold() for item in fields}
    best: tuple[int, float, str] | None = None
    for line in layout.lines:
        text = line.text.strip()
        if text.casefold() in claimed or not is_plausible_text(text):
            continue
        if not 3 <= len(text) <= 80 or re.search(r"\d{4,}", text):
            continue
        if len(re.findall(r"[A-Za-z]{3,}", text)) < 2:
            continue
        rank = _TIER_RANK.get(line.tier, 0)
        if best is None or (rank, line.char_height) > (best[0], best[1]):
            best = (rank, line.char_height, text)
    return best[2] if best else None


def _looks_like_postal_code(value: str) -> bool:
    """True when a bare number is a postal code rather than a telephone number.

    Recognises the ZIP and ZIP+4 forms used in the United States, plus the five-digit European
    and Japanese forms, without assuming any particular country: the test is the shape of the
    number, not the digits themselves.
    """
    stripped = value.strip()
    # ZIP+4, written as five digits, a hyphen, then four more.
    if re.fullmatch(r"\d{5}-\d{4}", stripped):
        return True
    digits = re.sub(r"\D", "", stripped)
    if len(digits) != 5:
        return False
    # Five digits with no separator at all is a postal code. Telephone numbers are written with
    # a leading country or area code, or with separators.
    return not re.search(r"[()\s.\-/+]", stripped) or (
        stripped.count(" ") == 0 and len(stripped) == 5
    )


def _promote_unlabelled_numbers(
    winners: list[dict[str, Any]], pool: list[Candidate]
) -> list[dict[str, Any]]:
    """Give unlabelled telephone numbers the `phone` and `fax` keys.

    Plenty of cards print bare numbers with no `Tel:` prefix, so refusing to assign them
    would drop the single most reliable field on a card. Values already claimed by a
    printed `phone` or `fax` label are consumed first, and only genuinely distinct numbers
    are promoted, so a card with one number yields `phone` and a card with two yields
    `phone` and `fax`.
    """
    digit_runs = [candidate for candidate in pool if candidate.name == "phone_like"]
    if not digit_runs:
        return winners
    distinct: list[tuple[str, float, str, int]] = []
    for candidate in digit_runs:
        digits = _numeric_key(candidate.value)
        if not re.sub(r"\D", "", digits):
            continue
        # A postal code is not a telephone number. Promoting one produced a `phone` holding a
        # ZIP+4 and invented a `fax` alongside it, both of which the ground truth rejects. A
        # postal code is short, has no leading country or area code shape, and may carry the
        # ZIP+4 hyphen form.
        if _looks_like_postal_code(candidate.value):
            continue
        if any(_numeric_key(existing[2]) == digits for existing in distinct):
            continue
        distinct.append(
            (candidate.value, candidate.token_confidence, candidate.value, candidate.tier)
        )
    if not distinct:
        return winners
    ranked = sorted(distinct, key=lambda item: -item[1])

    taken: set[str] = set()
    for item in winners:
        if item["name"] in {"phone", "fax"}:
            taken.add(_numeric_key(str(item["value"])))

    additions: list[dict[str, Any]] = []
    for key in ("phone", "fax"):
        if any(item["name"] == key for item in winners):
            continue
        for value, token_confidence, _, tier in ranked:
            if _numeric_key(value) in taken:
                continue
            if not _is_plausible_phone(value):
                continue
            taken.add(_numeric_key(value))
            additions.append(
                {
                    "name": key,
                    "value": _normalize(value),
                    "confidence": round(min(0.88, 0.45 + token_confidence * 0.5), 3),
                    "source": "unlabelled_digit_run",
                    "evidence": {
                        "tier": tier,
                        "support": 1,
                        "token_confidence": round(float(token_confidence), 3),
                        "agreement": 0.5,
                    },
                }
            )
            break
    return [*winners, *additions] if additions else winners


def _resplit_organization_family(
    winners: list[dict[str, Any]], pool: list[Candidate]
) -> list[dict[str, Any]]:
    """Give the most prominent organisation-like line the generic `organization` key.

    A card can carry a parent body, a division and a laboratory at once, for example a
    university / department / library trio on one card. They are ranked typographically
    rather than by a fixed precedence, so the largest becomes `organization` while the rest
    keep their specific role.
    """
    family = {"organization", "company", "department", "institution", "laboratory"}
    present = {item["name"] for item in winners}
    if "organization" not in present or len(present & family) < 2:
        return winners
    heights: dict[str, float] = {}
    for candidate in pool:
        if candidate.name in family and candidate.line is not None:
            current = heights.get(candidate.name, 0.0)
            heights[candidate.name] = max(current, candidate.line.char_height)
    if len(heights) < 2:
        return winners
    ordered = sorted(heights, key=lambda name: (-heights[name], name))
    if ordered[0] != "organization":
        return winners
    taken = {item["name"] for item in winners if item["name"] != "organization"}
    promoted: str | None = None
    for other in ordered[1:]:
        if other in taken:
            continue
        promoted = "department" if other in {"department", "laboratory"} else other
        break
    if promoted is None:
        return winners
    return [
        {**item, "name": promoted, "source": f"{item['source']}+typographic_rank"}
        if item["name"] == "organization"
        else item
        for item in winners
    ]


def _merge_identity(name: str, value: str) -> str:
    if name in {"phone", "phone_like", "fax", "nik"}:
        return f"{name}:{_numeric_key(value)}"
    if name in {"email", "website", "url"}:
        return f"{name}:{_key_of(value)}"
    if name in {"date", "money", "percent"}:
        return f"{name}:{_key_of(value)}"
    return f"{name}:{_key_of(value)}"


def _value_similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, _key_of(left), _key_of(right)).ratio()


def _vote(candidates: list[Candidate], variant_count: int) -> list[dict[str, Any]]:
    grouped: dict[str, list[Candidate]] = {}
    for candidate in candidates:
        grouped.setdefault(_merge_identity(candidate.name, candidate.value), []).append(candidate)
    scored: list[tuple[float, str, list[Candidate]]] = []
    for identity, group in grouped.items():
        support = len({id(candidate) for candidate in group})
        best = max(group, key=lambda candidate: candidate.weight)
        agreement = max(
            (
                _value_similarity(candidate.value, other.value)
                for candidate in group
                for other in group
            ),
            default=1.0,
        )
        consensus = 1.0 + 0.55 * (support - 1) + 0.25 * max(0.0, agreement - 0.6)
        confidence = min(
            0.99,
            best.weight * consensus * (0.85 + 0.15 * min(support / max(variant_count, 1), 1.0)),
        )
        scored.append((confidence, identity, group))
    scored.sort(key=lambda item: (-item[0], item[1]))
    winners: list[dict[str, Any]] = []
    used_names: set[str] = set()
    for _confidence, _identity, group in scored:
        name = group[0].name
        if name in used_names:
            continue
        best = max(group, key=lambda candidate: candidate.weight)
        used_names.add(name)
        winners.append(
            {
                "name": name,
                "value": _normalize(best.value),
                "confidence": round(float(confidence), 3),
                "source": best.source,
                "evidence": {
                    "tier": best.tier,
                    "support": len(group),
                    "token_confidence": round(float(best.token_confidence), 3),
                    "agreement": round(float(agreement), 3),
                },
            }
        )
    return winners


# --------------------------------------------------------------------------------------
# Document specific assembly
# --------------------------------------------------------------------------------------

_ID_ONLY_KEYS = {
    "provinsi",
    "kabupaten",
    "kota",
    "nama",
    "tempat_tgl_lahir",
    "jenis_kelamin",
    "gol_darah",
    "rt_rw",
    "kel_desa",
    "kecamatan",
    "agama",
    "status_perkawinan",
    "pekerjaan",
    "kewarganegaraan",
    "berlaku_hingga",
}

_CARD_KEYS = {
    "name",
    "title",
    "organization",
    "company",
    "department",
    "laboratory",
    "institution",
    "division",
    "email",
    "phone",
    "fax",
    "website",
    "address",
}

_RECEIPT_KEYS = {
    "ref_number",
    "date",
    "due_date",
    "subtotal",
    "tax",
    "tax_rate",
    "discount",
    "total",
    "billed_from",
    "billed_to",
}

_PHONE_LIKE_KEYS = {"phone_like"}


def _assemble_id(fields: list[dict[str, Any]], candidates: list[Candidate]) -> None:
    """A KTP is a label:value form, so anchored values are the trustworthy ones.

    The Indonesian key for a person's name is `nama`; an English `Name:` label maps onto it
    rather than being emitted as a second, competing key.
    """
    for position, item in enumerate(fields):
        if item["name"] == "name":
            fields[position] = {**item, "name": "nama", "source": f"{item['source']}+id_schema"}
    for item in fields:
        if item["name"] in _ID_ONLY_KEYS and str(item["source"]).startswith("label:"):
            item["confidence"] = min(0.99, item["confidence"] + 0.03)
    nik = next((item for item in fields if item["name"] == "nik"), None)
    if nik is not None:
        nik["confidence"] = min(0.99, nik["confidence"] + 0.05)
    del candidates


def _assemble_receipt(fields: list[dict[str, Any]]) -> dict[str, Any]:
    lookup = {item["name"]: item["value"] for item in fields}
    header: dict[str, Any] = {}
    for key in ("title", "ref_number", "date", "due_date"):
        if key in lookup:
            header[key] = lookup[key]
    summary: dict[str, Any] = {}
    for key in ("subtotal", "tax", "tax_rate", "discount", "total"):
        if key in lookup:
            summary[key] = lookup[key]
    sections: dict[str, Any] = {}
    for key in ("billed_from", "billed_to"):
        if key in lookup:
            sections[key] = lookup[key]
    structured: dict[str, Any] = {}
    if header:
        structured["header"] = header
    if sections:
        structured.update(sections)
    if summary:
        structured["summary"] = summary
    return structured


def _assemble_paper(fields: list[dict[str, Any]], best_layout: Layout | None) -> dict[str, Any]:
    lookup = {item["name"]: item["value"] for item in fields}
    # A form prints `Date:` where a voucher expects `voucher_date`; the same printed date
    # label therefore feeds the document-specific key.
    if "voucher_date" not in lookup and "date" in lookup:
        lookup["voucher_date"] = lookup["date"]
    header_keys = (
        "document_type",
        "vendor_name",
        "vendor_ntn",
        "voucher_no",
        "voucher_date",
        "inv_no",
        "company_code",
    )
    header = {key: lookup[key] for key in header_keys if key in lookup}
    signature_keys = ("prepared_by", "it_incharge", "branch_manager", "auditor")
    signatures = {key: lookup[key] for key in signature_keys if key in lookup}
    structured: dict[str, Any] = {}
    if header:
        structured["header"] = header
    if signatures:
        structured["signatures"] = signatures
    if "page_info" in lookup:
        structured["page_info"] = lookup["page_info"]
    elif best_layout is not None and best_layout.lines:
        for line in best_layout.lines:
            if re.search(r"page\s+\d+\s*(?:of|/)\s*\d+", line.text, re.IGNORECASE):
                structured["page_info"] = line.text
                break
    return structured


def parse_all(
    ocr_results: list[OcrResult],
    width: int = 1,
    height: int = 1,
    requested_type: str = "auto",
) -> Extraction:
    """Extract fields by pooling evidence from every OCR variant and voting per key."""
    extraction = Extraction()
    if not ocr_results:
        return extraction
    # Classify from one coherent reading, not the concatenation of every variant. Joining
    # them multiplies the line count, which would make any card look like a dense document.
    reference = max(
        (result for result in ocr_results if result.text.strip()),
        key=lambda result: (len(result.text), result.confidence),
        default=ocr_results[0],
    )
    classification = classify_document(reference.text, width, height, requested_type)
    extraction.document_type = classification.document_type
    extraction.classification = classification.to_dict()

    pool: list[Candidate] = []
    variant_count = max(len(ocr_results), 1)
    best_layout: Layout | None = None
    for result in ocr_results:
        if not result.text.strip():
            continue
        scale = 0.6 + 0.4 * min(len(ocr_results) / 8, 1.0)
        pool.extend(_tier1_from_text(result.text, max(result.confidence, 0.05) * scale))
        layout = build_layout(result, width, height)
        if layout.lines and (best_layout is None or len(layout.lines) > len(best_layout.lines)):
            best_layout = layout
        pool.extend(_tier2_from_layout(layout, scale))
        pool.extend(_tier34_from_layout(layout, scale))

    if not pool:
        extraction.unclassified = [
            {
                "text": line.text,
                "confidence": round(line.confidence / 100, 3),
                "reason": "no_rule_matched",
            }
            for line in (best_layout.lines if best_layout else [])
        ]
        return extraction

    winners = _vote(pool, variant_count)
    winners = _prefer_complete_values(winners, pool)
    document_type = extraction.document_type
    if document_type not in {"paper_document", "receipt"}:
        # A debit note or invoice is full of bare numbers in table columns; promoting those
        # to a telephone number would be nonsense, so promotion is limited to card-like
        # documents where a long digit run really is a contact detail.
        winners = _promote_unlabelled_numbers(winners, pool)
    if document_type == "id_card":
        keep = _ID_ONLY_KEYS | {"nik", "alamat", "name"}
        fields = [item for item in winners if item["name"] in keep]
        _assemble_id(fields, pool)
        extraction.fields = fields
    elif document_type == "receipt":
        fields = [
            item for item in winners if item["name"] in _RECEIPT_KEYS | {"title", "email", "phone"}
        ]
        extraction.fields = fields
        extraction.structured = _assemble_receipt(winners)
    elif document_type == "paper_document":
        fields = [
            item
            for item in winners
            if item["name"] not in {"phone_like", "money", "percent", "name"}
        ]
        # A form or note names itself on its most prominent line; that is the document type.
        if not any(item["name"] in {"document_type", "title"} for item in fields):
            heading = _document_heading(best_layout, fields)
            if heading is not None:
                fields.insert(
                    0,
                    {
                        "name": "document_type",
                        "value": heading,
                        "confidence": 0.62,
                        "source": "prominent_heading",
                        "evidence": {
                            "tier": 4,
                            "support": 1,
                            "token_confidence": 0.6,
                            "agreement": 0.5,
                        },
                    },
                )
        extraction.fields = fields
        extraction.structured = _assemble_paper(winners, best_layout)
    else:
        fields = [item for item in winners if item["name"] in _CARD_KEYS]
        extraction.fields = _resplit_organization_family(fields, pool)

    for item in extraction.fields:
        shaped = _enforce_key_shape(str(item["name"]), str(item["value"]))
        if shaped is None:
            item["value"] = ""
            item["suppressed"] = True
        elif shaped != item["value"]:
            item["value"] = shaped
    extraction.fields = [item for item in extraction.fields if not item.get("suppressed")]

    claimed_values = {item["value"].casefold() for item in extraction.fields}
    if best_layout is not None:
        leftover: list[LineBlock] = []
        for line in best_layout.lines:
            if line.text.casefold() in claimed_values:
                continue
            if _match_label(line.text) is not None:
                continue
            leftover.append(line)

        # Everything the typed pass did not claim is still information. It is grouped by
        # where it sits on the card rather than by a fixed label list, because the whole
        # point is that no schema rule matched it. Discarding it is what made a card with a
        # printed department and a three-line address score as if the text were absent.
        for block in _group_residual(leftover):
            extraction.unclassified.append(
                {
                    "text": block["value"],
                    "confidence": block["confidence"],
                    "reason": "no_field_rule_matched",
                    "tier": block["tier"],
                    "label": block["label"],
                    "inferred": block["inferred"],
                    "line_count": len(block["lines"]),
                }
            )
            pool.append(
                Candidate(
                    block["label"] or "unlabeled_text",
                    block["value"],
                    2,
                    "residual_block",
                    block["confidence"],
                    best_layout,
                    block["anchor"],
                )
            )

        if extraction.fields:
            _recover_from_residual(extraction.fields, pool, best_layout)

    all_lines = best_layout.lines if best_layout else []
    plausible_lines = sum(1 for line in all_lines if is_plausible_text(line.text, 0.5))
    plausible_characters = sum(
        len(line.text) for line in all_lines if is_plausible_text(line.text, 0.5)
    )
    strong_fields = [item for item in extraction.fields if item["confidence"] >= 0.6]
    token_confidences = [result.confidence for result in ocr_results if result.confidence]
    extraction.evidence = {
        "ocr_variants": len(ocr_results),
        "candidates_considered": len(pool),
        "keys_recovered": len(extraction.fields),
        "lines_seen": len(all_lines),
        "plausible_line_ratio": (round(plausible_lines / len(all_lines), 3) if all_lines else 0.0),
        # How much real text was read, as opposed to how confident a few fragments were.
        # A tight zoom on one corner is highly confident but incomplete, so coverage has to
        # outweigh confidence when a crop is chosen.
        "plausible_characters": plausible_characters,
        "mean_token_confidence": (
            round(sum(token_confidences) / len(token_confidences), 4) if token_confidences else 0.0
        ),
        "strong_field_ratio": (
            round(len(strong_fields) / len(extraction.fields), 3) if extraction.fields else 0.0
        ),
        "candidates_per_key": {
            key: sum(1 for candidate in pool if candidate.name == key)
            for key in sorted({candidate.name for candidate in pool})
        },
    }
    return extraction


def parse_fields(
    text: str,
    requested_type: str = "auto",
    width: int = 1,
    height: int = 1,
) -> dict[str, Any]:
    """Backwards compatible single-result entry point used by the existing unit tests."""
    result = OcrResult(text, 0.7, text.splitlines(), None, {"variant": "text_only"}, [])
    extraction = parse_all([result], width, height, requested_type)
    return {
        "document_type": extraction.document_type,
        "classification": extraction.classification,
        "fields": extraction.fields,
        "structured": extraction.structured,
        "unclassified": extraction.unclassified,
    }


def summarise_confidence(fields: list[dict[str, Any]]) -> float:
    if not fields:
        return 0.0
    return round(float(statistics.mean(item["confidence"] for item in fields)), 4)
