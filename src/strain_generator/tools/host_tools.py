import json
import logging
from functools import lru_cache
from typing import NamedTuple, Optional
import requests
from importlib.resources import files


CLB_BASE = "https://api.checklistbank.org"
GBIF_BASE = "https://api.gbif.org/v1"
GBIF_BACKBONE_KEY = "d7dddbf4-2cf0-4f39-9b2a-bb099caae36c"

logger = logging.getLogger(__name__)


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


@lru_cache(maxsize=1)
def _load_vernacular_index() -> dict:
    """Map each lowercased vernacular name to its curated spelling.

    Covers host_map.json species and group names, plus host_name.json values
    so names generated in legacy mode still decode. host_map.json wins when
    both spell the same name.
    """
    index = {v.lower(): v for v in _load_host_dict().values() if v}
    host_map = _load_host_map()
    for entry in host_map["species"].values():
        index[entry["name"].lower()] = entry["name"]
    for group in host_map["groups"].values():
        index[group["name"].lower()] = group["name"]
    return index


def segment_to_vernacular(segment: str) -> str:
    """Reverse the host segment of a strain name to a vernacular name.

    The generator lowercases the vernacular and writes its spaces as "_"
    (see main.normalize_host). This restores the spaces and returns the
    curated spelling when there is one, e.g. "domestic_turkey" ->
    "Domestic Turkey", "duck" -> "Duck". A name not in either table, such as
    one that came from the GBIF fallback, is returned with spaces restored
    and otherwise as written.
    """
    name = segment.replace("_", " ")
    return _load_vernacular_index().get(name.lower(), name)


# ---------------------------------------------------------------------------
# Host map: species + common-name groups (data/host_map.json)
# ---------------------------------------------------------------------------

# Words that say how sure the sampler was, not what the host is.
FILLER_WORDS = {"unknown", "unidentified", "sp", "sp.", "spp", "spp."}

# Match types from ChecklistBank that name the taxon asked for. "higherrank"
# (a parent stood in for an unknown name) and "none" are rejected.
COL_ACCEPTED_MATCH_TYPES = ("exact", "variant")


class HostResolution(NamedTuple):
    """How a host string resolved.

    Attributes:
        label:      Curated display name written to the host segment
                    ("Mallard", "Duck").
        col_name:   Scientific name to match in COL for the strain ID.
        usage_id:   COL usage ID when resolution already matched it, else None.
        matched_by: "species", "group", "member", "head_noun", "col" or "gbif".
    """
    label: str
    col_name: str
    usage_id: Optional[str]
    matched_by: str


@lru_cache(maxsize=1)
def _load_host_map() -> dict:
    host_json = files("strain_generator.data").joinpath("host_map.json")
    with open(host_json, "r", encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def _host_map_indexes() -> dict:
    """Lookup tables over host_map.json, built once.

    Returns a dict of:
        common:  lowercased species/group name or group label -> (kind, key)
        members: member taxon name -> group label
        heads:   head noun -> group label
    """
    host_map = _load_host_map()
    common, members, heads = {}, {}, {}
    for sci, entry in host_map["species"].items():
        common[entry["name"].lower()] = ("species", sci)
    for label, group in host_map["groups"].items():
        common[label] = ("group", label)
        common[group["name"].lower()] = ("group", label)
        for member in group["members"]:
            members[member] = label
        for head in group["heads"]:
            heads[head] = label
    return {"common": common, "members": members, "heads": heads}


def species_vernacular(scientific_name: str) -> Optional[str]:
    """Curated vernacular for a species, from host_map.json then host_name.json.

    Returns None when neither table has the species.
    """
    norm = normalize_host(scientific_name)
    entry = _load_host_map()["species"].get(norm)
    if entry:
        return entry["name"]
    return _load_host_dict().get(norm) or None


def _plural_variants(text: str) -> list:
    """The text itself, then forms with a plural "s" or "es" removed."""
    variants = [text]
    if text.endswith("es"):
        variants.append(text[:-2])
    if text.endswith("s"):
        variants.append(text[:-1])
    return variants


def _species_result(sci: str, matched_by: str) -> HostResolution:
    return HostResolution(_load_host_map()["species"][sci]["name"], sci, None, matched_by)


def _group_result(label: str, matched_by: str, col_name: Optional[str] = None,
                  usage_id: Optional[str] = None) -> HostResolution:
    group = _load_host_map()["groups"][label]
    return HostResolution(group["name"], col_name or group["taxon"], usage_id, matched_by)


def _match_head_noun(words: list) -> Optional[str]:
    """Group label for the longest trailing run of words that is a head noun."""
    heads = _host_map_indexes()["heads"]
    for start in range(len(words)):
        for candidate in _plural_variants(" ".join(words[start:])):
            if candidate in heads:
                return heads[candidate]
    return None


def get_classification(dataset_key, usage_id, session=None) -> list:
    """Ancestor names of a COL usage, nearest first.

    For a synonym, ChecklistBank includes the accepted taxon as the nearest
    entry, so a synonym walks up through its accepted name.
    """
    sess = session or requests
    resp = sess.get(
        f"{CLB_BASE}/dataset/{dataset_key}/taxon/{usage_id}/classification",
        headers={"Accept": "application/json"},
        timeout=30,
    )
    resp.raise_for_status()
    names = []
    for rec in resp.json():
        name = rec.get("name")
        names.append(name.get("scientificName") if isinstance(name, dict) else name)
    return [n for n in reversed(names) if n]


def _resolve_scientific(sci: str, dataset_key, session) -> Optional[HostResolution]:
    """Place a scientific name: the table, a group member, or a COL walk-up.

    Returns None when COL has no exact match for the name.

    Raises:
        ValueError: If COL matches the name but no host group covers it.
    """
    norm = normalize_host(sci)
    if norm in _load_host_map()["species"]:
        return _species_result(norm, "species")
    members = _host_map_indexes()["members"]
    if norm in members:
        return _group_result(members[norm], "member", col_name=norm)

    taxon = match_species(norm, dataset_key, session=session)
    if not taxon or taxon["match_type"] not in COL_ACCEPTED_MATCH_TYPES:
        return None
    for ancestor in get_classification(dataset_key, taxon["usage_id"], session=session):
        if ancestor in members:
            return _group_result(members[ancestor], "col", col_name=norm,
                                 usage_id=taxon["usage_id"])
    raise ValueError(
        f"{sci!r} matched {taxon['scientific_name']!r} in COL, but no host group "
        f"in host_map.json covers it"
    )


def gbif_vernacular_to_scientific(common_name, session=None) -> Optional[str]:
    """Look up the one GBIF backbone species whose English name is common_name.

    Only accepted species whose English vernacular equals the input
    (ignoring case) count; GBIF's search ranks loose matches such as hybrids
    and subspecies first.

    Returns:
        The canonical scientific name, or None when no species qualifies.

    Raises:
        ValueError: If more than one species carries that exact name.
    """
    sess = session or requests
    resp = sess.get(
        f"{GBIF_BASE}/species/search",
        params={"q": common_name, "qField": "VERNACULAR",
                "datasetKey": GBIF_BACKBONE_KEY, "limit": 50},
        timeout=30,
    )
    resp.raise_for_status()
    target = common_name.casefold()
    found = set()
    for rec in resp.json().get("results", []):
        if rec.get("rank") != "SPECIES" or rec.get("taxonomicStatus") != "ACCEPTED":
            continue
        if not rec.get("canonicalName"):
            continue
        for vn in rec.get("vernacularNames", []):
            if vn.get("language") in ("eng", None) and \
                    (vn.get("vernacularName") or "").casefold() == target:
                found.add(rec["canonicalName"])
                break
    if len(found) > 1:
        raise ValueError(
            f"common name {common_name!r} is ambiguous in GBIF: "
            f"{', '.join(sorted(found))}; give the scientific name"
        )
    return found.pop() if found else None


def resolve_host(text: str, dataset_key, session=None) -> HostResolution:
    """Resolve a scientific or common host name against host_map.json.

    Tried in order, stopping at the first hit:
      1. Exact scientific name: a species key, or a group member taxon.
      2. Exact common name: a species name, a group label or group name,
         allowing a plural.
      3. Head noun: the longest trailing words of the name that are a group
         head ("cinnamon teal" -> duck, "Steller's sea lion" -> seal).
      4. COL: an exact match in the pinned release, walked up its
         classification to the nearest group member.
      5. GBIF: the species whose English name is exactly the input, then
         placed as in 1 and 4.
    Steps 3-5 log a warning naming what matched.

    Args:
        text:        Host as the user gave it.
        dataset_key: Pinned COL dataset key (package.yaml COL_dataset_key).
        session:     Optional requests.Session for the network steps.

    Returns:
        HostResolution.

    Raises:
        ValueError: If nothing resolves, if COL matches a taxon no group
                    covers, or if the GBIF name is ambiguous.
    """
    raw = " ".join(text.replace("_", " ").split())
    words = [w for w in raw.lower().split() if w not in FILLER_WORDS]
    common = " ".join(words)
    if not common:
        raise ValueError(f"host {text!r} names no host")

    host_map = _load_host_map()
    indexes = _host_map_indexes()

    # 1. Exact scientific name (offline)
    sci = normalize_host(common)
    if sci in host_map["species"]:
        return _species_result(sci, "species")
    if sci in indexes["members"]:
        return _group_result(indexes["members"][sci], "member", col_name=sci)

    # 2. Exact common name (offline)
    for candidate in _plural_variants(common):
        hit = indexes["common"].get(candidate)
        if hit:
            kind, key = hit
            if kind == "species":
                return _species_result(key, "species")
            return _group_result(key, "group")

    # 3. Head noun (offline)
    label = _match_head_noun(words)
    if label:
        logger.warning(
            "host %r matched group %r by its head noun; give the scientific name "
            "for a species-level ID", text, label,
        )
        return _group_result(label, "head_noun")

    # 4. COL walk-up for a scientific name not in the table
    result = _resolve_scientific(common, dataset_key, session)
    if result:
        logger.warning("host %r is not in host_map.json; placed in group %r via COL",
                       text, result.label)
        return result

    # 5. GBIF: common name -> scientific name
    gbif_sci = gbif_vernacular_to_scientific(common, session=session)
    if gbif_sci:
        result = _resolve_scientific(gbif_sci, dataset_key, session)
        if result:
            logger.warning("host %r resolved through GBIF to %r (%s)",
                           text, gbif_sci, result.label)
            return result._replace(matched_by="gbif")

    labels = ", ".join(sorted(host_map["groups"]))
    raise ValueError(
        f"could not resolve host {text!r}; give a scientific name or one of the "
        f"host groups: {labels}"
    )


def gbif_match_usage_key(scientific_name, session=None):
    """Match a scientific name to a GBIF backbone usage key.

    Returns the usageKey, or None if GBIF reports no match. Matching is
    non-strict, so FUZZY matches are accepted.
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

    Consults the local host_name.json table first. If that misses and
    use_fallback is set, falls back to GBIF (backbone match -> vernacular
    lookup with preferred-flag ranking). Returns None if nothing resolves.
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


def match_species(species_name, dataset_key, session=None):
    """Match a name against a specific, pinned dataset key."""
    sess = session or requests
    resp = sess.get(
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
