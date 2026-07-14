from __future__ import annotations

from datetime import date, datetime
from hashlib import sha256
from io import BytesIO
import math
import re
from typing import Any

from openpyxl import load_workbook
from openpyxl.utils.datetime import to_excel
from pydantic import BaseModel, computed_field

from app.schemas.wealth_portfolio import IGNORED_SHEETS, ImportIssue


SUPPORTED_SHEETS = frozenset({
    "BALANCE SHEET",
    "CURRENT ASSET",
    "FUNDS",
    "Funds XIRR",
    "Final XIRR",
    "EQUITY",
    "FIXED ASSET",
    "GOALS",
    "MNTHLY INCOM PLAN",
    "Gera office roi",
})


class ParsedAsset(BaseModel):
    source_key: str
    name: str
    asset_type: str
    category: str | None = None
    account_owner: str | None = None
    account_type: str | None = None
    market: str = "IN"
    currency: str = "INR"
    invested_amount: float | None = None
    market_value: float | None = None
    source_ref: dict[str, Any]


class ParsedTransaction(BaseModel):
    source_key: str
    asset_source_key: str
    occurred_on: date
    kind: str = "BUY"
    amount: float
    units: float | None = None
    unit_price: float | None = None
    currency: str = "INR"
    source_ref: dict[str, Any]


class ParsedValuation(BaseModel):
    source_key: str
    asset_source_key: str
    valued_on: date
    market_value: float
    currency: str = "INR"
    source_ref: dict[str, Any]


class ParsedWorkbook(BaseModel):
    source_sha256: str
    filename: str
    recognized_sheets: list[str]
    ignored_sheets: list[str]
    assets: list[ParsedAsset]
    transactions: list[ParsedTransaction]
    valuations: list[ParsedValuation]
    issues: list[ImportIssue]

    @computed_field
    @property
    def counts(self) -> dict[str, int]:
        return {
            "assets": len(self.assets),
            "transactions": len(self.transactions),
            "valuations": len(self.valuations),
        }


def _header(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def _name(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (date, datetime)):
        number = float(to_excel(value))
        return number if math.isfinite(number) else None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        text = value.strip()
        for pattern in ("%Y-%m-%d", "%d %b %Y", "%d-%m-%Y", "%d/%m/%Y"):
            try:
                return datetime.strptime(text, pattern).date()
            except ValueError:
                continue
    return None


def _source_key(*parts: Any) -> str:
    normalized = "|".join(_name(part).casefold() for part in parts)
    return sha256(normalized.encode("utf-8")).hexdigest()


def _rows(sheet, required_heading: str | None = None) -> tuple[dict[str, int], list[tuple[int, tuple[Any, ...]]]]:
    all_rows = list(sheet.iter_rows(values_only=True))
    header_index = 0
    if required_heading:
        for index, row in enumerate(all_rows[:20]):
            if required_heading.casefold() in {_header(value) for value in row}:
                header_index = index
                break
    if not all_rows:
        return {}, []
    headings = all_rows[header_index]
    columns = {_header(value): index for index, value in enumerate(headings) if _header(value)}
    return columns, [
        (row_number, row)
        for row_number, row in enumerate(all_rows[header_index + 1 :], start=header_index + 2)
    ]


def _value(row: tuple[Any, ...], columns: dict[str, int], *names: str) -> Any:
    for name in names:
        index = columns.get(name.casefold())
        if index is not None and index < len(row):
            return row[index]
    return None


def _parse_funds(sheet) -> tuple[list[ParsedAsset], list[ImportIssue]]:
    columns, rows = _rows(sheet, "fund name")
    if "fund name" not in columns:
        columns, rows = _rows(sheet, "fund")
    assets: list[ParsedAsset] = []
    issues: list[ImportIssue] = []
    for row_number, row in rows:
        serial = _value(row, columns, "s no.", "s no", "sno")
        name = _name(_value(row, columns, "fund", "fund name", "scheme"))
        if not name:
            continue
        if "fund name" in columns and not isinstance(serial, (int, float)):
            continue
        invested = _number(_value(row, columns, "principal", "invested", "investment"))
        market_value = _number(_value(row, columns, "market value", "current value", "value"))
        if invested is None and market_value is None:
            issues.append(ImportIssue(
                severity="warning", code="fund_without_value",
                message=f"{name} has no principal or market value", sheet="FUNDS", row=row_number,
            ))
            continue
        assets.append(ParsedAsset(
            source_key=_source_key(
                "fund", _value(row, columns, "name", "owner"),
                _value(row, columns, "mode"), name, _value(row, columns, "acc type"),
            ),
            name=name,
            asset_type="mutual_fund",
            category=_name(_value(row, columns, "category")) or None,
            account_owner=_name(_value(row, columns, "name", "owner")) or None,
            account_type=_name(_value(row, columns, "acc type")) or None,
            invested_amount=invested,
            market_value=market_value,
            source_ref={"sheet": "FUNDS", "row": row_number},
        ))
    return assets, issues


def _parse_flat_fund_transactions(sheet, assets: list[ParsedAsset]) -> tuple[list[ParsedTransaction], list[ParsedValuation], list[ImportIssue]]:
    columns, rows = _rows(sheet)
    transactions: list[ParsedTransaction] = []
    issues: list[ImportIssue] = []
    assets_by_name = {asset.name.casefold(): asset for asset in assets}
    for row_number, row in rows:
        name = _name(_value(row, columns, "fund", "fund name", "scheme"))
        if not name:
            continue
        occurred_on = _date(_value(row, columns, "date", "transaction date"))
        if occurred_on is None:
            issues.append(ImportIssue(
                severity="error", code="invalid_transaction_date",
                message=f"{name} has an invalid transaction date", sheet="Funds XIRR", row=row_number,
            ))
            continue
        amount = _number(_value(row, columns, "amount", "invested"))
        if amount is None or amount <= 0:
            issues.append(ImportIssue(
                severity="error", code="invalid_transaction_amount",
                message=f"{name} has an invalid transaction amount", sheet="Funds XIRR", row=row_number,
            ))
            continue
        asset = assets_by_name.get(name.casefold())
        if asset is None:
            issues.append(ImportIssue(
                severity="error", code="unknown_transaction_asset",
                message=f"{name} is not present in FUNDS", sheet="Funds XIRR", row=row_number,
            ))
            continue
        units = _number(_value(row, columns, "units"))
        nav = _number(_value(row, columns, "nav", "unit price"))
        transactions.append(ParsedTransaction(
            source_key=_source_key("fund-buy", name, occurred_on.isoformat(), amount, units, nav),
            asset_source_key=asset.source_key,
            occurred_on=occurred_on,
            amount=amount,
            units=units,
            unit_price=nav,
            source_ref={"sheet": "Funds XIRR", "row": row_number},
        ))
    return transactions, [], issues


def _parse_paired_fund_transactions(sheet, assets: list[ParsedAsset]) -> tuple[list[ParsedTransaction], list[ParsedValuation], list[ImportIssue]]:
    rows = list(sheet.iter_rows(values_only=True))
    transactions: list[ParsedTransaction] = []
    valuations: list[ParsedValuation] = []
    issues: list[ImportIssue] = []
    if len(rows) < 4:
        return transactions, valuations, issues

    assets_by_owner_name = {
        ((asset.account_owner or "").casefold(), asset.name.casefold()): asset
        for asset in assets
    }
    assets_by_name = {asset.name.casefold(): asset for asset in assets}
    width = max((len(row) for row in rows), default=0)
    for date_column in range(0, width, 2):
        amount_column = date_column + 1
        owner = _name(rows[0][date_column] if date_column < len(rows[0]) else None)
        fund_name = _name(rows[1][date_column] if date_column < len(rows[1]) else None)
        if not fund_name:
            continue
        asset = assets_by_owner_name.get((owner.casefold(), fund_name.casefold())) or assets_by_name.get(fund_name.casefold())
        if asset is None:
            issues.append(ImportIssue(
                severity="error", code="unknown_transaction_asset",
                message=f"{fund_name} is not present in FUNDS", sheet="Funds XIRR", row=2,
            ))
            continue
        for row_number, row in enumerate(rows[3:], start=4):
            raw_date = row[date_column] if date_column < len(row) else None
            raw_amount = row[amount_column] if amount_column < len(row) else None
            if raw_date is None and raw_amount is None:
                continue
            occurred_on = _date(raw_date)
            amount = _number(raw_amount)
            if (occurred_on is not None and raw_amount is None) or (raw_date is None and amount is not None):
                issues.append(ImportIssue(
                    severity="warning", code="incomplete_cash_flow",
                    message=f"{fund_name} has an incomplete cash-flow pair and was skipped",
                    sheet="Funds XIRR", row=row_number,
                ))
                continue
            if occurred_on is None or amount is None:
                issues.append(ImportIssue(
                    severity="error", code="invalid_transaction_date" if occurred_on is None else "invalid_transaction_amount",
                    message=f"{fund_name} has an invalid XIRR cash-flow row", sheet="Funds XIRR", row=row_number,
                ))
                continue
            if amount < 0:
                transactions.append(ParsedTransaction(
                    source_key=_source_key("fund-buy", owner, fund_name, occurred_on.isoformat(), abs(amount)),
                    asset_source_key=asset.source_key,
                    occurred_on=occurred_on,
                    amount=abs(amount),
                    source_ref={"sheet": "Funds XIRR", "row": row_number, "column": date_column + 1},
                ))
            elif amount > 0:
                valuations.append(ParsedValuation(
                    source_key=_source_key("valuation", owner, fund_name, occurred_on.isoformat(), amount),
                    asset_source_key=asset.source_key,
                    valued_on=occurred_on,
                    market_value=amount,
                    source_ref={"sheet": "Funds XIRR", "row": row_number, "column": date_column + 1},
                ))
    return transactions, valuations, issues


def _parse_fund_transactions(sheet, assets: list[ParsedAsset]) -> tuple[list[ParsedTransaction], list[ParsedValuation], list[ImportIssue]]:
    first_row = next(sheet.iter_rows(values_only=True), ())
    normalized = {_header(value) for value in first_row}
    if "date" in normalized or "transaction date" in normalized:
        return _parse_flat_fund_transactions(sheet, assets)
    return _parse_paired_fund_transactions(sheet, assets)


def parse_workbook(payload: bytes, filename: str) -> ParsedWorkbook:
    source_sha256 = sha256(payload).hexdigest()
    workbook = load_workbook(BytesIO(payload), read_only=True, data_only=True)
    recognized = [name for name in workbook.sheetnames if name in SUPPORTED_SHEETS]
    ignored = [name for name in workbook.sheetnames if name in IGNORED_SHEETS]
    issues: list[ImportIssue] = []

    assets: list[ParsedAsset] = []
    if "FUNDS" in recognized:
        assets, fund_issues = _parse_funds(workbook["FUNDS"])
        issues.extend(fund_issues)

    transactions: list[ParsedTransaction] = []
    valuations: list[ParsedValuation] = []
    if "Funds XIRR" in recognized:
        transactions, valuations, transaction_issues = _parse_fund_transactions(workbook["Funds XIRR"], assets)
        issues.extend(transaction_issues)

    if not valuations:
        latest_transaction_date = max((item.occurred_on for item in transactions), default=date.today())
        valuations = [
            ParsedValuation(
                source_key=_source_key("valuation", asset.source_key, latest_transaction_date.isoformat(), asset.market_value),
                asset_source_key=asset.source_key,
                valued_on=latest_transaction_date,
                market_value=asset.market_value,
                source_ref=asset.source_ref,
            )
            for asset in assets
            if asset.market_value is not None
        ]

    parsed_sheets = {"FUNDS", "Funds XIRR"}
    for sheet_name in recognized:
        if sheet_name not in parsed_sheets:
            issues.append(ImportIssue(
                severity="warning",
                code="sheet_parser_pending",
                message=f"{sheet_name} was recognized but is not normalized in the foundation phase",
            ))

    return ParsedWorkbook(
        source_sha256=source_sha256,
        filename=filename,
        recognized_sheets=recognized,
        ignored_sheets=ignored,
        assets=assets,
        transactions=transactions,
        valuations=valuations,
        issues=issues,
    )
