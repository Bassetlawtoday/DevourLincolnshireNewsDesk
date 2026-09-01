from openpyxl import Workbook
from openpyxl.styles import Font


def export_excel(results, filename):

    wb = Workbook()

    ws = wb.active

    ws.title = "Planning Report"

    headings = [
        "Planning Reference",
        "Address/Site",
        "Proposal",
        "Current Status",
        "Decision",
        "Decision Date",
        "Notes"
    ]

    ws.append(headings)

    for cell in ws[1]:
        cell.font = Font(bold=True)

    for row in results:
        ws.append([
            row["Planning Reference"],
            row["Address/Site"],
            row["Proposal"],
            row["Current Status"],
            row["Decision"],
            row["Decision Date"],
            row["Notes"]
        ])

    wb.save(filename)