from datetime import date
from io import BytesIO

from openpyxl import Workbook


def make_workbook_bytes(*, invalid_transaction_date: bool = False) -> bytes:
    workbook = Workbook()
    funds = workbook.active
    funds.title = "FUNDS"
    funds.append(["Fund", "Principal", "Market Value", "Category"])
    funds.append(["Example Mid Cap", 400000, 520000, "Mid cap"])

    xirr = workbook.create_sheet("Funds XIRR")
    xirr.append(["Fund", "Date", "Amount", "Units", "NAV"])
    xirr.append([
        "Example Mid Cap",
        "not-a-date" if invalid_transaction_date else date(2025, 3, 6),
        400000,
        4025.481297,
        99.367,
    ])

    for sheet_name in (
        "BALANCE SHEET", "CURRENT ASSET", "Final XIRR", "EQUITY",
        "FIXED ASSET", "GOALS", "MNTHLY INCOM PLAN", "Gera office roi",
    ):
        workbook.create_sheet(sheet_name)

    ignored = workbook.create_sheet("MF discont.")
    ignored.append(["DO_NOT_EXPOSE"])
    workbook.create_sheet("Property Cal.")
    workbook.create_sheet("REMIT")
    workbook.create_sheet("STOCKS RECMDN")

    stream = BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def make_real_layout_workbook_bytes(
    *, include_incomplete_cash_flow: bool = False, date_formatted_amount: bool = False,
    include_amount_without_date: bool = False,
) -> bytes:
    workbook = Workbook()
    funds = workbook.active
    funds.title = "FUNDS"
    funds.append([None, None, None, "Last Updated", date(2026, 4, 25)])
    funds.append(["S NO.", "NAME", "MODE", "FUND NAME", "CATEGORY", "DATE STARTED", "LAST UPDATED", "PRINCIPAL", "MARKET VALUE"])
    funds.append([1, "Nishi", "Lumpsum", "Example Mid Cap", "MID_CAP", None, date(2025, 3, 6), 405000, 493000])
    funds.append([None, "Nishi", "Lumpsum", "SUB TOTAL", None, None, None, 405000, 493000])

    xirr = workbook.create_sheet("Funds XIRR")
    xirr.append(["Nishi", "MID_CAP"])
    xirr.append(["Example Mid Cap", None])
    xirr.append(["XIRR", 0.18])
    xirr.append([date(2025, 1, 27), -5000])
    if date_formatted_amount:
        xirr.cell(row=4, column=2).number_format = "dd-mmm-yyyy"
    xirr.append([date(2025, 3, 6), -400000])
    xirr.append([date(2026, 4, 25), 493000])
    if include_incomplete_cash_flow:
        xirr.append([date(2025, 4, 1), None])
    if include_amount_without_date:
        xirr.append([None, -10000])

    stream = BytesIO()
    workbook.save(stream)
    return stream.getvalue()
