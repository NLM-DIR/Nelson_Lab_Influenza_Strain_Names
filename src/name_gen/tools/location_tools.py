import pycountry

from name_gen import logger
from name_gen.tools import utils
import unicodedata
import difflib


def normalize(s):
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.lower().split())


def find_subdivision(subdivisions, subdivision_name):
    target = normalize(subdivision_name)
    subs = list(subdivisions)

    # 1. exact match on normalized names
    for s in subs:
        if normalize(s.name) == target:
            return s.code

    # 2. fuzzy fallback
    names = {normalize(s.name): s.code for s in subs}
    close = difflib.get_close_matches(target, names.keys(), n=1, cutoff=0.85)
    if close:
        return names[close[0]]

    return None


def get_country_and_subdivision(country_name, subdivision_name=None):
    country = pycountry.countries.search_fuzzy(country_name)[0]
    display_name = getattr(
        country, "common_name",
        getattr(country, "name", getattr(country, "official_name", None)),
    )
    if subdivision_name is None:
        return display_name, "0"
    subdivisions = pycountry.subdivisions.get(country_code=country.alpha_2)
    subdivision_code = find_subdivision(subdivisions, subdivision_name)
    if subdivision_code is None:
        logger.warning(f"No match found for subdivision: {subdivision_name}")
        return display_name, country.alpha_2
    return display_name, subdivision_code


def get_local_code(subdivision_code):
    if len(subdivision_code) == 2:
        return "0"
    else:
        local_string = subdivision_code.split("-")[1]
        return subdivision_to_code(local_string)


def subdivision_to_code(subdivision_code: str) -> str:
    # This could be refactored. It is a little awkward.
    if not subdivision_code:
        return "0"

    code = ""
    subdivision_code.replace("-", "")

    for char in subdivision_code:
        code += utils.letter_to_num(char)
    return code


def num_to_letter(num: str) -> str:
    """
    Takes two-digit position in alphabet and returns the letter.
    "01" -> "a"
    """
    return chr(int(num) + 96)


def code_to_subdivision(code: str) -> str:
    result = ""
    i = 0
    while i < len(code):
        if code[i] == "-":
            result += "-"
            i += 1
        else:
            result += num_to_letter(code[i:i + 2]).upper()
            i += 2
    return result
