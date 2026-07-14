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
