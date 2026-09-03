"""Small dependency-free helpers shared across the package.

This module must stay free of imports so that `csv_handler` can use it
without pulling in the network-touching modules.
"""

# Canonical scientific name for human samples. The pipeline resolves hosts as
# scientific names, so the human flag/column must expand to this rather than to
# the vernacular "Human", which COL cannot match.
HUMAN_SCIENTIFIC_NAME = "Homo sapiens"


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
