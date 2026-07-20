"""
csv_processor: Batch generation of influenza strain names from a CSV file.

Reads an input CSV containing sample metadata, validates that the required
columns are present, generates a strain name for each row, and writes an
updated CSV with a new strain-name column.
"""

import csv
from datetime import datetime
from typing import Callable

from tqdm import tqdm

# Columns that must always be present in the input CSV header.
REQUIRED_COLUMNS = [
    "virus_type",
    "location",
    "country",
    "sequence",
    "lab_id",
    "date",
]

# Either "host" or "human" must be present to determine the host species.
HOST_COLUMNS = ["host", "human"]

# Values in a "human" column that are treated as truthy.
TRUE_VALUES = {"1", "true", "t", "yes", "y"}

DATE_FORMAT = "%Y-%m-%d"


def _validate_columns(fieldnames: list[str]) -> None:
    """Raise ValueError if any required column is missing from the header."""
    if not fieldnames:
        raise ValueError("Input CSV has no header row.")

    present = set(fieldnames)
    missing = [col for col in REQUIRED_COLUMNS if col not in present]
    if missing:
        raise ValueError(
            "Input CSV is missing required column(s): "
            + ", ".join(missing)
            + f". Required columns are: {', '.join(REQUIRED_COLUMNS)}."
        )

    if not any(col in present for col in HOST_COLUMNS):
        raise ValueError(
            "Input CSV must contain a 'host' column, a 'human' column, or both."
        )


def _resolve_host(row: dict) -> str:
    """Determine the host for a row, honoring an optional 'human' column.

    A truthy 'human' value yields "Human". Otherwise the 'host' value is used,
    which must be non-empty.
    """
    human_flag = (row.get("human") or "").strip().lower()
    if human_flag in TRUE_VALUES:
        return "Human"

    host = (row.get("host") or "").strip()
    if not host:
        raise ValueError("'host' is required unless 'human' is set.")
    return host


def _row_to_strain_name(
    row: dict,
    assemble_fn: Callable,
) -> str:
    """Build a strain name from a single CSV row."""
    host = _resolve_host(row)

    raw_date = (row.get("date") or "").strip()
    try:
        collection_date = datetime.strptime(raw_date, DATE_FORMAT)
    except ValueError:
        raise ValueError(f"'date' must be in {DATE_FORMAT} format, got: {raw_date!r}")

    return assemble_fn(
        virus_type=(row.get("virus_type") or "").strip(),
        host=host,
        location=(row.get("location") or "").strip(),
        country=(row.get("country") or "").strip(),
        sequence=(row.get("sequence") or "").strip(),
        lab_id=(row.get("lab_id") or "").strip(),
        collection_date=collection_date,
    )


def process_csv(
    input_path: str,
    output_path: str,
    strain_column: str,
    assemble_fn: Callable,
) -> tuple[int, list[tuple[int, str]]]:
    """Read a metadata CSV, generate strain names, and write an updated CSV.

    Rows that fail (bad date, missing host, or an error raised by assemble_fn)
    are skipped and collected for reporting; valid rows are still written.

    Args:
        input_path:    Path to the input CSV file.
        output_path:   Path to write the updated CSV (may equal input_path).
        strain_column: Name of the new column to hold generated strain names.
        assemble_fn:   Function with the signature of assemble_strain_name.

    Returns:
        A tuple of (number of rows successfully named, list of (row_number,
        error_message) for skipped rows).

    Raises:
        FileNotFoundError: If input_path does not exist.
        ValueError:        If the header is missing required columns.
    """
    errors: list[tuple[int, str]] = []
    with open(input_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        _validate_columns(reader.fieldnames)
        fieldnames = list(reader.fieldnames)
        if strain_column not in fieldnames:
            fieldnames.append(strain_column)
        # Materialize rows up front so tqdm can show a total, percentage, and ETA.
        input_rows = list(reader)

    rows = []
    # enumerate starts at 2 because row 1 is the header in the source file.
    for i, row in tqdm(
        enumerate(input_rows, start=2),
        total=len(input_rows),
        desc="Generating strain names",
        unit="row",
    ):
        try:
            row[strain_column] = _row_to_strain_name(row, assemble_fn)
        except Exception as exc:
            errors.append((i, str(exc)))
            continue
        rows.append(row)

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows), errors
