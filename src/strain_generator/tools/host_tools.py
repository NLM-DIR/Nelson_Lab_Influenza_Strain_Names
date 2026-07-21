import json
from functools import lru_cache
import requests
from importlib.resources import files


CLB_BASE = "https://api.checklistbank.org"
GBIF_BASE = "https://api.gbif.org/v1"


def normalize_host(host_string: str) -> str:
    host_string = host_string.strip().replace("_", " ").lower()
    # Capitalize first letter only (genus capitalized, species lowercase)
    return host_string[:1].upper() + host_string[1:]


@lru_cache(maxsize=1)
def _load_host_dict() -> dict:
    host_json = files("strain_generator.data").joinpath("host_name.json")
    with open(host_json, "r") as f:
        return json.load(f)


def get_canon_name(host_string: str) -> str:
    """Convert the user provided scientific name to the canonical common name.

    Args:
        host_string (str): user latin name
    Returns:
        str: canonical host name
    Raises:
        KeyError: if the scientific name is not in the lookup table
    """
    norm_host = normalize_host(host_string)
    host_dict = _load_host_dict()
    try:
        return host_dict[norm_host]
    except KeyError:
        raise KeyError(f"Unknown host: {host_string!r} (normalized: {norm_host!r})")


def gbif_match_usage_key(scientific_name, session=None):
    """Match a scientific name to a GBIF backbone usage key.

    Returns the usageKey, or None if there's no confident match.
    """
    sess = session or requests
    resp = sess.get(
        f"{GBIF_BASE}/species/match",
        params={"name": scientific_name, "strict": "false"},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    # matchType is EXACT, FUZZY, HIGHERRANK, or NONE. Reject NONE.
    # Treat FUZZY with caution: it can silently match the wrong taxon.
    if data.get("matchType") == "NONE":
        return None

    return data.get("usageKey")


def gbif_vernacular_name(usage_key, language="en", session=None):
    """Fetch vernacular names for a GBIF usage key and pick the best one.

    Selection order:
      1. A name flagged `preferred` in the target language.
      2. Any name in the target language.
      3. None (caller should fall back).

    GBIF uses ISO 639-1 codes ("en"), unlike COL's 639-3 ("eng").
    The endpoint is paged; one page (default 20) is plenty for a single
    taxon, but we page through defensively in case preferred names sit later.
    """
    sess = session or requests
    candidates = []
    offset = 0
    limit = 100

    while True:
        resp = sess.get(
            f"{GBIF_BASE}/species/{usage_key}/vernacularNames",
            params={"limit": limit, "offset": offset},
            timeout=30,
        )
        resp.raise_for_status()
        payload = resp.json()

        for rec in payload.get("results", []):
            if rec.get("language") != language:
                continue
            candidates.append(
                (bool(rec.get("preferred")), rec.get("vernacularName"))
            )

        if payload.get("endOfRecords", True):
            break
        offset += limit

    if not candidates:
        return None

    # Prefer flagged names; otherwise take the first in-language name.
    for is_preferred, name in candidates:
        if is_preferred and name:
            return name
    return candidates[0][1]


@lru_cache()
def scientific_to_vernacular(scientific_name, language="eng", session=None,
                             use_fallback=True):
    """Resolve a scientific name to its best-matching vernacular name.

    Tries GBIF (backbone match -> vernacular lookup with preferred-flag
    ranking), then falls back to the local VERNACULAR_FALLBACK map.
    Returns None if nothing resolves.
    """

    try:
        return get_canon_name(scientific_name)
    except KeyError:
        pass

    if use_fallback:
        sess = session or requests
        try:
            usage_key = gbif_match_usage_key(scientific_name, session=sess)
            if usage_key is not None:
                name = gbif_vernacular_name(usage_key, language=language,
                                            session=sess)
                if name:
                    return name
        except requests.RequestException:
            # Network/HTTP failure — fall through to local map rather than raise.
            pass

    return None


def resolve_latest_dataset_key():
    """Resolve the '3LR' latest-release alias to its concrete dataset key + version."""
    resp = requests.get(
        f"{CLB_BASE}/dataset/3LR",
        headers={"Accept": "application/json"},
        timeout=30,
    )
    resp.raise_for_status()
    meta = resp.json()
    # 'key' is the concrete integer dataset key; 'version'/'alias' give the human label
    return {
        "dataset_key": meta.get("key"),
        "version": meta.get("version") or meta.get("alias"),
        "title": meta.get("title"),
    }


def match_species(species_name, dataset_key):
    """Match a name against a specific, pinned dataset key."""
    resp = requests.get(
        f"{CLB_BASE}/dataset/{dataset_key}/match/nameusage",
        params={"q": species_name},
        headers={"Accept": "application/json"},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    usage = data.get("usage")
    if not usage:
        return None
    return {
        "usage_id": usage.get("id"),
        "scientific_name": usage.get("label"),
        "status": usage.get("status"),
        "match_type": data.get("type"),
    }


def get_species_name(dataset_key, usage_id):
    """
    Reverse lookup: resolve a stored (dataset_key, usage_id) reference back
    to its scientific name against the exact COL release it was recorded in.

    dataset_key: the concrete integer dataset key stored at sampling time
                 (NOT the '3LR' alias).
    usage_id:    the alphanumeric COL usage ID.

    Returns a dict with the resolved name and provenance, or None if the
    usage no longer exists in that dataset.
    """
    resp = requests.get(
        f"{CLB_BASE}/dataset/{dataset_key}/nameusage/{usage_id}",
        headers={"Accept": "application/json"},
        timeout=30,
    )
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    data = resp.json()

    name = data.get("name", {})
    result = {
        "usage_id": data.get("id"),
        "scientific_name": name.get("scientificName") or data.get("label"),
        "authorship": name.get("authorship"),
        "rank": name.get("rank") or data.get("rank"),
        "status": data.get("status"),
        "dataset_key": dataset_key,
    }

    # If the stored ID resolves to a synonym, surface the accepted name too,
    # so callers can distinguish the recorded concept from the current accepted one.
    accepted = data.get("accepted")
    if accepted:
        acc_name = accepted.get("name", {})
        result["accepted_usage_id"] = accepted.get("id")
        result["accepted_scientific_name"] = (
            acc_name.get("scientificName") or accepted.get("label")
        )

    return result
