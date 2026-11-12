"""Small dependency-free helpers shared across the package.

This module must stay free of package and third-party imports so that
`csv_handler` can use it without pulling in the network-touching modules.
"""

from functools import wraps

# Canonical scientific name for human samples. The pipeline resolves hosts as
# scientific names, so the human flag/column must expand to this rather than to
# the vernacular "Human", which COL cannot match.
HUMAN_SCIENTIFIC_NAME = "Homo sapiens"


def parse_year(raw: str, label: str = "year") -> int:
    """Parse a collection year, which must be exactly 4 digits.

    Args:
        raw:   The year as given, e.g. "2026". Surrounding whitespace is ignored.
        label: How to name the input in the error message ("--year", "'year'").

    Returns:
        The year as an int.

    Raises:
        ValueError: If the value is not exactly 4 ASCII digits.
    """
    norm = (raw or "").strip()
    if len(norm) != 4 or not (norm.isascii() and norm.isdigit()):
        raise ValueError(f"{label} must be a 4-digit year, e.g. 2026, got: {raw!r}")
    return int(norm)


def letter_to_num(char: str) -> str:
    """
    Takes letter and returns position in alphabet. Single digits prefixed with "0".

    "a" -> "01"
    """
    number = str(ord(char.lower()) - 96)
    if len(number) == 1:
        return "0" + number
    else:
        return number


def space_to_underscore(func):
    """Decorator: replace spaces with underscores in the wrapped function's
    string result. Applied to the host segment only; the reader reverses it
    with host_tools.segment_to_vernacular."""
    @wraps(func)
    def inner(*args, **kwargs):
        return func(*args, **kwargs).replace(" ", "_")
    return inner