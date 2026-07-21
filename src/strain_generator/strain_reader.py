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
import argparse
import json
import sys

CLB_BASE_URL = "https://api.checklistbank.org"

COL_Version = {
    1: 315448,
}


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

    strain_id = <taxonomy_code>-<lab_identifier>-<month>
    taxonomy_code = <usage_id>.<dataset_key>
    """
    # Split into exactly 3 sections. The lab identifier may itself contain
    # additional characters, so limit the split.
    taxonomy_code, sample_id, lab_identifier, month = strain_id.split("-", 3)

    usage_id, dataset_key = taxonomy_code.split(".", 1)
    dataset_key = COL_Version.get(int(dataset_key))

    scientific_name = resolve_scientific_name(dataset_key, usage_id, session=session)

    return {
        "taxonomy_code": taxonomy_code,
        "col_dataset_key": dataset_key,
        "col_usage_id": usage_id,
        "scientific_name": scientific_name,
        "month": month,
        "lab_identifier": f"{sample_id}-{lab_identifier}",
    }


def decode_strain_name(strain_name, session=None):
    """Decode a full influenza strain name into a metadata dictionary."""
    virus_type, host, location, strain_id, year = strain_name.split("/")

    sid = decode_strain_id(strain_id, session=session)

    return {
        "virus_type": virus_type,
        "host": {
            "vernacular_name": host,
            "scientific_name": sid["scientific_name"],
            "col_dataset_key": sid["col_dataset_key"],
            "col_usage_id": sid["col_usage_id"],
        },
        "location": decode_location(location),
        "date": {
            "month": sid["month"],
            "year": year,
        },
        "lab_identifier": sid["lab_identifier"],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="strain-read",
        description=(
            "Decode an influenza isolate strain name into structured metadata. "
            "Strain name format: <type>/<host>/<location>/<strain_id>/<year>"
        ),
    )
    parser.add_argument(
        "strain_name",
        metavar="STRAIN_NAME",
        help=(
            "The strain name to decode, e.g. "
            "'A/Domestic Chicken/US-NY/3F72J.1-002_NEL26-06/2026'"
        ),
    )
    parser.add_argument(
        "-o",
        "--output",
        type=argparse.FileType("w"),
        default=sys.stdout,
        help="Write JSON output to a file instead of stdout.",
    )
    parser.add_argument(
        "--indent",
        type=int,
        default=2,
        help="Indentation level for JSON output (default: 2).",
    )
    args = parser.parse_args(argv)

    # Reuse a session to avoid re-establishing the connection on repeated calls.
    with requests.Session() as session:
        try:
            result = decode_strain_name(args.strain_name, session=session)
        except ValueError as exc:
            # split() failures: malformed strain name or strain ID.
            print(
                f"Malformed strain name {args.strain_name!r}: {exc}",
                file=sys.stderr,
            )
            return 1
        except requests.RequestException as exc:
            # Network / HTTP errors from ChecklistBank.
            print(
                f"Failed to resolve taxonomy for {args.strain_name!r}: {exc}",
                file=sys.stderr,
            )
            return 1

    json.dump(result, args.output, indent=args.indent)
    args.output.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
