from src.field_parser import parse_fields


def test_business_card_parser() -> None:
    result = parse_fields(
        "SAMPLE DATA\nAyu Prameswari\nNorthwind Studio\nayu@example.com\n+62 812 3456 7890"
    )
    values = {field["name"]: field["value"] for field in result["fields"]}
    assert result["document_type"] == "business_card"
    assert values["email"] == "ayu@example.com"
    assert "+62" in values["phone"]


def test_id_card_parser_uses_printed_labels() -> None:
    result = parse_fields("NIK: 3273010101990001\nNama: Example User\nTanggal Lahir: 1999-01-01")
    values = {field["name"]: field["value"] for field in result["fields"]}
    assert result["document_type"] == "id_card"
    assert values["nik"] == "3273010101990001"
    assert values["nama"] == "Example User"
    assert values["tempat_tgl_lahir"] == "1999-01-01"


def test_id_card_reports_english_printed_labels() -> None:
    result = parse_fields("NIK: 3273010101990001\nName: Example User\nDate of Birth: 1999-01-01")
    values = {field["name"]: field["value"] for field in result["fields"]}
    assert values["nik"] == "3273010101990001"
    assert values["tempat_tgl_lahir"] == "1999-01-01"


def test_receipt_parser() -> None:
    result = parse_fields("SAMPLE CORNER SHOP\nDate: 2026-05-01\nSubtotal 30000\nTOTAL 33000")
    values = {field["name"]: field["value"] for field in result["fields"]}
    structured = result["structured"]
    assert result["document_type"] == "receipt"
    assert values["total"] == "33000"
    assert structured["summary"]["total"] == "33000"


def test_paper_document_exposes_nested_header() -> None:
    text = (
        "STOCK DEBIT NOTE\n"
        "Voucher No: 15134112\n"
        "Voucher Date: 23/12/2025\n"
        "Item Code Description Qty Total Margin\n"
        "123 Sample Item 2 50000 10%"
    )
    result = parse_fields(text, width=3508, height=2481)
    assert result["document_type"] == "paper_document"
    header = result["structured"]["header"]
    assert header["voucher_no"] == "15134112"
    assert header["voucher_date"] == "23/12/2025"


def test_confidence_is_derived_per_field() -> None:
    result = parse_fields("Ayu Prameswari\nayu@example.com")
    for field in result["fields"]:
        assert 0.0 <= field["confidence"] <= 1.0
        assert field["evidence"]["tier"] in {1, 2, 3, 4}
        assert field["source"]


def test_unreadable_text_produces_no_confident_fields() -> None:
    result = parse_fields("~ ~ ~ ~ ~ ~ ~ ~ ~")
    assert result["fields"] == []
