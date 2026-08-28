"""Employee directory exports.

One column definition drives both formats, so a CSV and a spreadsheet of the same
filter always contain the same data. Adding a column means adding one row to
:data:`EXPORT_COLUMNS` and nothing else.

**No sensitive value is ever exported.** Bank details and government identifiers
are absent from the column list entirely rather than masked, because a masked
value in a spreadsheet is noise: it cannot be used for anything, and its presence
invites someone to ask for the unmasked version "just for this file".
"""

from __future__ import annotations

import csv
import io
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from app.models.employee import Employee
from app.models.enums import AddressType
from app.schemas.employee import ExportFormat

#: Excel silently truncates a sheet name past this, which would leave two exports
#: with the same tab name.
_MAX_SHEET_NAME = 31


@dataclass(frozen=True)
class ExportColumn:
    """One column of the export."""

    header: str
    value: Callable[[Employee], Any]
    width: int = 18


def _master_name(record: Any) -> str:
    return record.name if record is not None else ""


def _address_line(employee: Employee, address_type: AddressType) -> str:
    address = employee.address_of(address_type.value)
    return address.single_line if address is not None else ""


#: The export, in the order a reader expects to meet the fields: who they are,
#: then where they sit, then the terms of their employment.
EXPORT_COLUMNS: tuple[ExportColumn, ...] = (
    ExportColumn("Employee ID", lambda e: e.employee_code, 14),
    ExportColumn("First name", lambda e: e.first_name),
    ExportColumn("Last name", lambda e: e.last_name),
    ExportColumn("Official email", lambda e: e.official_email, 30),
    ExportColumn("Mobile", lambda e: e.mobile_number or "", 16),
    ExportColumn("Status", lambda e: e.employment_status.replace("_", " ").title(), 14),
    ExportColumn("Joining date", lambda e: e.joining_date, 14),
    ExportColumn("Confirmation date", lambda e: e.confirmation_date, 16),
    ExportColumn("Business unit", lambda e: _master_name(e.business_unit), 22),
    ExportColumn("Team", lambda e: _master_name(e.team), 22),
    ExportColumn("Team", lambda e: _master_name(e.team), 20),
    ExportColumn("Designation", lambda e: _master_name(e.designation), 24),
    ExportColumn("Grade", lambda e: _master_name(e.grade), 12),
    ExportColumn("Employment type", lambda e: _master_name(e.employment_type), 18),
    ExportColumn("Work location", lambda e: _master_name(e.work_location), 20),
    ExportColumn("Work mode", lambda e: (e.work_mode or "").title(), 12),
    ExportColumn(
        "Reporting manager",
        lambda e: e.reporting_manager.full_name if e.reporting_manager else "",
        24,
    ),
    ExportColumn("Gender", lambda e: (e.gender or "").replace("_", " ").title(), 14),
    ExportColumn("Date of birth", lambda e: e.date_of_birth, 14),
    ExportColumn("Blood group", lambda e: e.blood_group or "", 12),
    ExportColumn("Marital status", lambda e: (e.marital_status or "").title(), 14),
    ExportColumn("Nationality", lambda e: e.nationality or "", 16),
    ExportColumn("Personal email", lambda e: e.personal_email or "", 30),
    ExportColumn("Emergency contact", lambda e: e.emergency_contact_name or "", 22),
    ExportColumn("Emergency number", lambda e: e.emergency_contact_number or "", 18),
    ExportColumn("Current address", lambda e: _address_line(e, AddressType.CURRENT), 40),
    ExportColumn("Permanent address", lambda e: _address_line(e, AddressType.PERMANENT), 40),
)


def _as_text(value: Any) -> str:
    """Render a value for CSV, where everything is a string."""
    if value is None:
        return ""
    if isinstance(value, date | datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    return str(value)


def build_csv(employees: Sequence[Employee]) -> bytes:
    """Render the directory as CSV.

    Encoded UTF-8 **with a BOM**: without it, Excel on Windows opens the file in
    the system codepage and mangles every non-ASCII name. Every other consumer
    tolerates the BOM.

    ``QUOTE_ALL`` because an address containing a comma is the norm, not an edge
    case, and quoting everything removes a class of bug rather than one instance.
    """
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, quoting=csv.QUOTE_ALL, lineterminator="\r\n")

    writer.writerow([column.header for column in EXPORT_COLUMNS])
    for employee in employees:
        writer.writerow([_as_text(column.value(employee)) for column in EXPORT_COLUMNS])

    return buffer.getvalue().encode("utf-8-sig")


def build_xlsx(employees: Sequence[Employee], *, sheet_title: str = "Employees") -> bytes:
    """Render the directory as a spreadsheet.

    Dates are written as real dates rather than strings, so sorting and filtering
    in Excel behave; the header row is frozen and an autofilter applied, because
    a 3,000-row export is unusable without both.
    """
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = sheet_title[:_MAX_SHEET_NAME]

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="1F2937")

    sheet.append([column.header for column in EXPORT_COLUMNS])
    for index, column in enumerate(EXPORT_COLUMNS, start=1):
        cell = sheet.cell(row=1, column=index)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(vertical="center")
        sheet.column_dimensions[get_column_letter(index)].width = column.width

    for employee in employees:
        sheet.append(
            [
                # Dates and numbers are passed through so Excel types them;
                # everything else becomes text.
                value if isinstance(value, date | datetime | Decimal | int) else _as_text(value)
                for value in (column.value(employee) for column in EXPORT_COLUMNS)
            ]
        )

    for row in sheet.iter_rows(min_row=2, min_col=1, max_col=len(EXPORT_COLUMNS)):
        for cell in row:
            if isinstance(cell.value, date | datetime):
                cell.number_format = "yyyy-mm-dd"

    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = f"A1:{get_column_letter(len(EXPORT_COLUMNS))}{sheet.max_row}"

    stream = io.BytesIO()
    workbook.save(stream)
    return stream.getvalue()


#: Content type and file extension per format, so the route does not carry a
#: second copy of this mapping.
EXPORT_MEDIA_TYPES: dict[ExportFormat, str] = {
    ExportFormat.CSV: "text/csv; charset=utf-8",
    ExportFormat.XLSX: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def render(employees: Sequence[Employee], export_format: ExportFormat) -> tuple[bytes, str]:
    """Render the directory and return the payload with its media type."""
    if export_format is ExportFormat.CSV:
        return build_csv(employees), EXPORT_MEDIA_TYPES[ExportFormat.CSV]
    return build_xlsx(employees), EXPORT_MEDIA_TYPES[ExportFormat.XLSX]


def filename_for(export_format: ExportFormat, *, today: date) -> str:
    """``employees-2026-08-03.csv`` -- dated so successive exports do not collide."""
    return f"employees-{today.isoformat()}.{export_format.value}"
