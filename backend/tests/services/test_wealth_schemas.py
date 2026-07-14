import pytest
from pydantic import ValidationError

from app.schemas.wealth_portfolio import ImportIssue, ImportPreview


def test_import_issue_rejects_sensitive_sheet_details():
    with pytest.raises(ValidationError):
        ImportIssue(
            severity="warning",
            code="ignored",
            message="must not leak",
            sheet="MF discont.",
            row=1,
        )


def test_preview_counts_only_error_severity_as_blocking():
    preview = ImportPreview(
        preview_token="token",
        source_sha256="a" * 64,
        recognized_sheets=["FUNDS"],
        ignored_sheets=["MF discont."],
        counts={"assets": 1, "transactions": 0, "valuations": 1},
        issues=[
            ImportIssue(severity="warning", code="stale", message="stale value"),
            ImportIssue(severity="error", code="date", message="invalid date", sheet="FUNDS", row=2),
        ],
    )
    assert preview.blocking_error_count == 1
