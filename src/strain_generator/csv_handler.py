"""
csv_processor: Batch generation of influenza strain names from a CSV file.

Reads an input CSV containing sample metadata, validates that the required
columns are present, generates a strain name for each row, and writes an
updated CSV with a new strain-name column and an error column. The input file
is never overwritten, and rows that fail are kept with their error message.

The optional "isolate_version" and "lab_passage" columns feed the trailing
suffix of the strain ID, and the optional "subtype" column is appended to the
year in parentheses; all three may be omitted entirely.
"""

import csv
import os
from datetime import datetime
from typing import Callable

import requests
from tqdm import tqdm

from strain_generator.tools.utils import HUMAN_SCIENTIFIC_NAME

# Columns that must always be present in the input CSV header.
REQUIRED_COLUMNS = [
    "virus_type",
    "location",
    "country",
    "sequence",
    "date",
]

# Either "host" or "human" must be present to determine the host species.
HOST_COLUMNS = ["host", "human"]

# Recognized but not required. An absent or empty value means "not set".
OPTIONAL_COLUMNS = ["isolate_version", "lab_passage", "subtype"]

# Values in a "human" column that are treated as truthy.
TRUE_VALUES = {"1", "true", "t", "yes", "y"}

DATE_FORMAT = "%Y-%m-%d"


def _validate_columns(fieldnames: list[str]) -> None:
    """Raise ValueError if the header is absent, is missing a required column,
    or has neither a 'host' nor a 'human' column."""
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

    A truthy 'human' value yields the canonical human scientific name.
    Otherwise the 'host' value is used, which must be non-empty.
    """
    human_flag = (row.get("human") or "").strip().lower()
    if human_flag in TRUE_VALUES:
        return HUMAN_SCIENTIFIC_NAME

    host = (row.get("host") or "").strip()
    if not host:
        raise ValueError("'host' is required unless 'human' is set.")
    return host


def _resolve_isolate_version(row: dict):
    """Read the optional 'isolate_version' column.

    Returns the version as an int, or None when the column is absent or empty.
    """
    raw = (row.get("isolate_version") or "").strip()
    if not raw:
        return None

    if not raw.isdigit() or int(raw) < 1:
        raise ValueError(
            f"'isolate_version' must be a positive integer, got: {raw!r}"
        )
    return int(raw)


def _resolve_lab_passage(row: dict) -> bool:
    """Read the optional 'lab_passage' column as a boolean."""
    return (row.get("lab_passage") or "").strip().lower() in TRUE_VALUES


def _resolve_subtype(row: dict):
    """Read the optional 'subtype' column.

    Returns the raw value, or None when the column is absent or empty.
    Validation is left to assemble_fn so that a malformed subtype produces
    the same message in file mode as it does in single mode.
    """
    return (row.get("subtype") or "").strip() or None


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
        collection_date=collection_date,
        isolate_version=_resolve_isolate_version(row),
        lab_passage=_resolve_lab_passage(row),
        subtype=_resolve_subtype(row),
    )


def _is_same_file(path_a: str, path_b: str) -> bool:
    """True if both paths name the same file, including via links."""
    if os.path.realpath(path_a) == os.path.realpath(path_b):
        return True
    return (
        os.path.exists(path_a)
        and os.path.exists(path_b)
        and os.path.samefile(path_a, path_b)
    )


def process_csv(
    input_path: str,
    output_path: str,
    strain_column: str,
    assemble_fn: Callable,
    error_column: str = "error",
) -> tuple[int, list[tuple[int, str]]]:
    """Read a metadata CSV, generate strain names, and write an updated CSV.

    Every input row is written. A row that fails (bad date, missing host, or a
    ValueError / requests.RequestException raised by assemble_fn) gets an
    empty strain name and its message in error_column, and is also collected
    for reporting. Any other exception signals a bug and propagates.

    Args:
        input_path:    Path to the input CSV file.
        output_path:   Path to write the updated CSV. Must not be input_path.
        strain_column: Name of the new column to hold generated strain names.
        assemble_fn:   Function with the signature of assemble_strain_name.
        error_column:  Name of the new column to hold per-row error messages.

    Returns:
        A tuple of (number of rows successfully named, list of (row_number,
        error_message) for failed rows).

    Raises:
        FileNotFoundError: If input_path does not exist.
        ValueError:        If output_path is the input file, or the header is
                           absent or missing required columns.
    """
    if _is_same_file(input_path, output_path):
        raise ValueError(
            f"output path {output_path!r} is the input file; the input file "
            f"is never overwritten"
        )

    errors: list[tuple[int, str]] = []
    with open(input_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        _validate_columns(reader.fieldnames)
        fieldnames = list(reader.fieldnames)
        for column in (strain_column, error_column):
            if column not in fieldnames:
                fieldnames.append(column)
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
            row[error_column] = ""
        except (ValueError, requests.RequestException) as exc:
            row[strain_column] = ""
            row[error_column] = str(exc)
            errors.append((i, str(exc)))
        rows.append(row)

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows) - len(errors), errors
