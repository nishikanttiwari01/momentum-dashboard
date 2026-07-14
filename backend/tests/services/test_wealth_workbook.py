from tests.fixtures.wealth_workbook_factory import make_workbook_bytes

from app.services.wealth_workbook import parse_workbook


def test_parser_extracts_assets_transactions_and_valuations():
    result = parse_workbook(make_workbook_bytes(), "investment.xlsx")
    assert result.counts == {"assets": 1, "transactions": 1, "valuations": 1}
    assert result.assets[0].name == "Example Mid Cap"
    assert result.transactions[0].occurred_on.isoformat() == "2025-03-06"


def test_parser_reports_ignored_sheet_without_reading_cells():
    result = parse_workbook(make_workbook_bytes(), "investment.xlsx")
    assert "MF discont." in result.ignored_sheets
    assert "DO_NOT_EXPOSE" not in result.model_dump_json()


def test_parser_assigns_same_source_key_on_repeat_parse():
    payload = make_workbook_bytes()
    first = parse_workbook(payload, "a.xlsx")
    second = parse_workbook(payload, "b.xlsx")
    assert first.transactions[0].source_key == second.transactions[0].source_key


def test_parser_reports_invalid_transaction_date_as_blocking_error():
    result = parse_workbook(make_workbook_bytes(invalid_transaction_date=True), "bad.xlsx")
    issue = next(item for item in result.issues if item.code == "invalid_transaction_date")
    assert issue.severity == "error"
    assert issue.sheet == "Funds XIRR"
    assert issue.row == 2
