import json
import logging
import unicodedata
from functools import lru_cache
from importlib.resources import files

import country_converter as coco
import pycountry
from rapidfuzz import process, fuzz

# coco logs its own warning for unmatched names; we raise a clearer error instead.
logging.getLogger("country_converter.country_converter").setLevel(logging.ERROR)

SCORE_CUTOFF = 70
AMBIGUITY_MARGIN = 5  # top two fuzzy scores closer than this are rejected


def normalize(s):
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.lower().split())


def _score(query, name, **kwargs):
    # Also score against the name's leading words so "Yunnan" matches
    # "Yunnan Sheng" without letting "York" match "New York".
    prefix = " ".join(name.split()[:len(query.split())])
    return max(fuzz.token_sort_ratio(query, name), fuzz.token_sort_ratio(query, prefix))


@lru_cache(maxsize=1)
def _load_location_aliases() -> dict:
    """Curated overrides for names pycountry or fuzzy matching gets wrong.

    Returns ``{alpha_2: {normalized name: subdivision code}}``.
    """
    alias_json = files("strain_generator.data").joinpath("location_aliases.json")
    with open(alias_json, "r", encoding="utf-8") as f:
        table = json.load(f)
    return {cc: {normalize(k): v for k, v in names.items()} for cc, names in table.items()}


@lru_cache(maxsize=None)
def _converter():
    # Building the converter compiles every country regex (~0.5 s); do it once.
    return coco.CountryConverter()


def resolve_country(country_name):
    """Resolve a country name or ISO code to its pycountry record.

    Raises:
        ValueError: if coco finds no match or more than one.
    """
    alpha_2 = _converter().convert(country_name, to="ISO2")
    if not isinstance(alpha_2, str) or alpha_2 == "not found":
        raise ValueError(f"could not match country {country_name!r} to an ISO 3166 entry")
    return pycountry.countries.get(alpha_2=alpha_2)


def find_subdivision(subdivisions, subdivision_name):
    """Match a subdivision name or code against one country's subdivisions.

    Accepts the full ISO code (``US-VA``), its local part (``VA``), or a name,
    fuzzily matched after case/accent normalization.

    Raises:
        ValueError: if nothing matches, or the best two name matches score
            within ``AMBIGUITY_MARGIN`` of each other.
    """
    subs = list(subdivisions)
    query = subdivision_name.strip().upper()
    for s in subs:
        if query in (s.code, s.code.split("-", 1)[1]):
            return s.code

    matches = process.extract(
        normalize(subdivision_name),
        [normalize(s.name) for s in subs],
        scorer=_score,
        score_cutoff=SCORE_CUTOFF,
        limit=2,
    )
    if not matches:
        raise ValueError(f"no ISO 3166-2 subdivision matches {subdivision_name!r}")
    if len(matches) == 2 and matches[0][1] - matches[1][1] < AMBIGUITY_MARGIN:
        first, second = (subs[m[2]] for m in matches)
        raise ValueError(
            f"subdivision {subdivision_name!r} is ambiguous: "
            f"{first.name} ({first.code}) or {second.name} ({second.code})"
        )
    return subs[matches[0][2]].code


def get_country_and_subdivision(country_name, subdivision_name=None):
    country = resolve_country(country_name)
    display_name = getattr(
        country, "common_name",
        getattr(country, "name", getattr(country, "official_name", None)),
    )
    if not (subdivision_name or "").strip():
        return display_name, "0"
    alias = _load_location_aliases().get(country.alpha_2, {}).get(normalize(subdivision_name))
    if alias:
        return display_name, alias
    subdivisions = pycountry.subdivisions.get(country_code=country.alpha_2) or []
    return display_name, find_subdivision(subdivisions, subdivision_name)
