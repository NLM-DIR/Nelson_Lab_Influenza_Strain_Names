"""
Decode influenza isolate strain names into structured metadata.

Strain name format:
    <type>/<host>/<location>/<strain_id>/<year>

Strain ID format:
    <taxonomy_code>-<month>-<lab_identifier>
    taxonomy_code = <col_dataset_key>.<col_usage_id>
"""

import requests
import pycountry

CLB_BASE_URL = "https://api.checklistbank.org"


def resolve_scientific_name(dataset_key, usage_id, session=None):
    """Query ChecklistBank (Catalogue of Life) for the scientific name
    of a name usage within a given COL release (dataset).

    Returns the scientific name string, or None if it can't be resolved.
    """
    sess = session or requests
    url = f"{CLB_BASE_URL}/dataset/{dataset_key}/nameusage/{usage_id}"
    resp = sess.get(url, headers={"Accept": "application/json"}, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    # The name usage object nests the parsed name under "name".
    # "scientificName" is the canonical string; fall back gracefully.
    name = data.get("name") or {}
    return (
        name.get("scientificName")
        or data.get("scientificName")
        or name.get("canonicalName")
    )


def decode_location(location):
    """Expand an ISO 3166 code into full names.

    Accepts either a bare country code ("US") or a
    country-subdivision code ("US-NY").

    Returns {"country": ..., "subdivision": ...}. Subdivision is None
    when only a country code is present. Values fall back to the raw
    code if lookup fails.
    """
    country_code = location.split("-", 1)[0]

    country = pycountry.countries.get(alpha_2=country_code)
    country_name = country.name if country else country_code

    subdivision_name = None
    if "-" in location:
        subdiv = pycountry.subdivisions.get(code=location)
        subdivision_name = subdiv.name if subdiv else location

    return {"country": country_name, "subdivision": subdivision_name}


def decode_strain_id(strain_id, session=None):
    """Break the strain ID into its components and resolve the taxonomy code.

    strain_id = <taxonomy_code>-<month>-<lab_identifier>
    taxonomy_code = <dataset_key>.<usage_id>
    """
    # Split into exactly 3 sections. The lab identifier may itself contain
    # additional characters, so limit the split.
    taxonomy_code, month, lab_identifier = strain_id.split("-", 2)

    dataset_key, usage_id = taxonomy_code.split(".", 1)

    scientific_name = resolve_scientific_name(dataset_key, usage_id, session=session)

    return {
        "taxonomy_code": taxonomy_code,
        "col_dataset_key": dataset_key,
        "col_usage_id": usage_id,
        "scientific_name": scientific_name,
        "month": month,
        "lab_identifier": lab_identifier,
    }


def decode_strain_name(strain_name, session=None):
    """Decode a full influenza strain name into a metadata dictionary."""
    virus_type, host, location, strain_id, year = strain_name.split("/")

    metadata = {
        "virus_type": virus_type,
        "host": host,
        "location": decode_location(location),
        "year": year,
    }
    metadata["strain_id"] = decode_strain_id(strain_id, session=session)
    return metadata


if __name__ == "__main__":
    example = "A/Domestic Chicken/US-NY/315448.3F72J-06-002_NEL26/2026"

    # Reuse a session to avoid re-establishing the connection on repeated calls.
    with requests.Session() as s:
        result = decode_strain_name(example, session=s)

    import json
    print(json.dumps(result, indent=2))