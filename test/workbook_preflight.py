"""Validate a sports-registration workbook locally and write a review report.

Usage:
    python3 workbook_preflight.py Students_data121212.xlsx

This utility never contacts the portal and never changes the source workbook.
Install project dependencies first with: pip install -r requirements.txt
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path
import re

import pandas as pd


MIN_PLAYER_AGE = 10
MAX_PLAYER_AGE = 14
DONE_VALUES = {"true", "1", "yes", "y"}


def normalise_column(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).strip().lower())


def find_column(columns: pd.Index, aliases: list[str], required: bool = True) -> str | None:
    names = {normalise_column(column): str(column) for column in columns}
    for alias in aliases:
        found = names.get(normalise_column(alias))
        if found is not None:
            return found
    if required:
        raise ValueError(f"Missing workbook column. Expected one of: {', '.join(aliases)}")
    return None


def is_complete(value: object) -> bool:
    return str(value).strip().casefold() in DONE_VALUES


def validate_row(row_index: int, row: pd.Series, columns: dict[str, str | None]) -> dict[str, object]:
    errors: list[str] = []
    student_name = str(row[columns["student"]]).strip()
    father_name = str(row[columns["father"]]).strip()
    gender = str(row[columns["gender"]]).strip()
    school = str(row[columns["school"]]).strip()
    dob = pd.to_datetime(row[columns["dob"]], errors="coerce")

    if not student_name or student_name.casefold() == "nan":
        errors.append("missing student name")
    if not father_name or father_name.casefold() == "nan":
        errors.append("missing parent name")
    if not gender or gender.casefold() == "nan":
        errors.append("missing gender")
    if not school or school.casefold() == "nan":
        errors.append("missing school")
    if pd.isna(dob):
        errors.append("invalid DOB")
    else:
        today = date.today()
        birth_date = dob.date()
        oldest_allowed = today.replace(year=today.year - MAX_PLAYER_AGE)
        youngest_allowed = today.replace(year=today.year - MIN_PLAYER_AGE)
        if not oldest_allowed < birth_date <= youngest_allowed:
            errors.append(f"outside {MIN_PLAYER_AGE}-{MAX_PLAYER_AGE} age range")

    done_column = columns["done"]
    status = "completed" if done_column and is_complete(row[done_column]) else "pending"
    return {
        "source_row": row_index + 2,
        "status": status,
        "validation": "valid" if not errors else "invalid",
        "issues": "; ".join(errors),
    }


def validate_workbook(path: Path, workers: int) -> pd.DataFrame:
    frame = pd.read_excel(path, engine="openpyxl")
    columns = {
        "school": find_column(frame.columns, ["School Management", "School Managment", "School Managemnt", "School"]),
        "student": find_column(frame.columns, ["Student Name", "Student"]),
        "father": find_column(frame.columns, ["Father's Name", "Fathers Name", "Father Name"]),
        "gender": find_column(frame.columns, ["Gender"]),
        "dob": find_column(frame.columns, ["DOB", "Date of Birth"]),
        "done": find_column(frame.columns, ["Done", "Completed"], required=False),
    }

    indexed_rows = list(frame.iterrows())
    with ThreadPoolExecutor(max_workers=workers) as executor:
        reports = list(
            executor.map(
                lambda item: validate_row(item[0], item[1], columns),
                indexed_rows,
            )
        )
    return pd.DataFrame(reports)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate a registration workbook without changing it.")
    parser.add_argument("workbook", type=Path, help="Path to the Excel workbook")
    parser.add_argument("--workers", type=int, default=4, help="Local validation threads (default: 4)")
    args = parser.parse_args()

    if not args.workbook.is_file():
        parser.error(f"Workbook not found: {args.workbook}")
    if args.workers < 1:
        parser.error("--workers must be at least 1")

    report = validate_workbook(args.workbook, args.workers)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = args.workbook.with_name(f"{args.workbook.stem}_preflight_{timestamp}.csv")
    report.to_csv(report_path, index=False)

    pending = report[report["status"] == "pending"]
    valid_pending = pending[pending["validation"] == "valid"]
    invalid = report[report["validation"] == "invalid"]
    print(f"Rows checked: {len(report)}")
    print(f"Valid pending rows: {len(valid_pending)}")
    print(f"Invalid rows: {len(invalid)}")
    print(f"Report written: {report_path}")


if __name__ == "__main__":
    main()