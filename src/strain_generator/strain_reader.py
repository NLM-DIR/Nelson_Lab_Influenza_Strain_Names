"""
Decode influenza isolate strain names into structured metadata.

Strain name format:
    <type>/<host>/<location>/<strain_id>/<year>[(<subtype>)]

The host segment is omitted for human samples, giving the 4-segment form:
    <type>/<location>/<strain_id>/<year>[(<subtype>)]

The host segment is the lowercased vernacular name with spaces written as
"_" ("domestic_turkey"). Both shapes decode the host to its host_name.json
spelling ("Domestic Turkey") when the table has it.

The year carries an optional parenthesised influenza subtype, e.g.
"2026(H5N1)". It is absent from names whose subtype was not recorded.

Strain ID format:
    <sequence>-<taxonomy_code>[-<suffix>]
    taxonomy_code = <col_usage_id>.<col_version>

col_version is an index into COL_Version, which maps it to the concrete
Catalogue of Life dataset key the usage ID was minted against, and into
ID_FORMATS, which gives the strain-ID layout used by names carrying that
index. The layout is taken from the version the name itself carries, never
from the generator's configuration, so names written against an earlier COL
release stay readable after a new one is adopted.

The suffix is optional and is one of "v<N>" (isolate version), "L" (lab
passage strain), or "v<N>.L" (both).
"""

import re
import requests
import pycountry
import argparse
import json
import sys

from strain_generator.tools import host_tools

CLB_BASE_URL = "https://api.checklistbank.org"

COL_Version = {
    1: 315448,
}

# Strain-ID layout used by names carrying each COL version index, given as the
# hyphen-separated fields in order. "suffix" is the optional field and may be
# absent from a given ID; every other field is required. Keep this keyed the
# same way as COL_Version: adopting a new COL release means adding its index to
# both, and a name's own index is what selects its layout.
#
# Index 1 originally carried a lab ID ("sequence", "lab_id", "taxonomy_code",
# "suffix"). Its layout was deliberately replaced when the lab ID was dropped,
# so names containing a lab ID no longer decode. Do not repeat this for future
# changes: register a new index instead.
ID_FORMATS = {
    1: ("sequence", "taxonomy_code", "suffix"),
}

# The taxonomy field of a strain ID: "<usage_id>.<col_version>".
TAXONOMY_RE = re.compile(r"^(?P<usage_id>[A-Za-z0-9]+)\.(?P<col_version>\d+)$")

# Optional trailing segment of the strain ID: "v2", "L", or "v2.L".
SUFFIX_RE = re.compile(
    r"^(?:v(?P<version>\d+)(?:\.(?P<version_passage>L))?|(?P<passage>L))$"
)

# Final name segment: a 4-digit year with an optional parenthesised subtype.
# The subtype body excludes "(", ")" and "/" so it cannot swallow a delimiter.
YEAR_RE = re.compile(r"^(?P<year>\d{4})(?:\((?P<subtype>[^()/]+)\))?$")


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


def decode_isolate_suffix(suffix):
    """Split the optional trailing segment of a strain ID.

    Returns a tuple of (isolate_version, lab_passage), where isolate_version
    is an int or None.

    Raises:
        ValueError: If the suffix is not "v<N>", "L", or "v<N>.L".
    """
    match = SUFFIX_RE.match(suffix)
    if not match:
        raise ValueError(
            f"unrecognized suffix {suffix!r}; expected 'v<N>', 'L', or 'v<N>.L'"
        )

    version = match.group("version")
    lab_passage = bool(match.group("version_passage") or match.group("passage"))

    return (int(version) if version else None), lab_passage


def decode_year_segment(segment):
    """Split the final name segment into its year and optional subtype.

    Returns a tuple of (year, subtype), where year is the 4-digit string and
    subtype is None when the name records no subtype.

    Raises:
        ValueError: If the segment is not "YYYY" or "YYYY(<subtype>)".
    """
    match = YEAR_RE.match(segment)
    if not match:
        raise ValueError(
            f"unrecognized year segment {segment!r}; expected 'YYYY' or "
            f"'YYYY(<subtype>)'"
        )

    return match.group("year"), match.group("subtype")


def describe_id_format(col_version):
    """Render an ID_FORMATS entry as a readable field template.

    Args:
        col_version: COL version index registered in ID_FORMATS.

    Returns:
        e.g. "<sequence>-<usage_id>.1[-<suffix>]".
    """
    rendered = ""
    for field in ID_FORMATS[col_version]:
        if field == "suffix":
            rendered += "[-<suffix>]"
            continue
        token = (
            f"<usage_id>.{col_version}" if field == "taxonomy_code" else f"<{field}>"
        )
        rendered += f"-{token}" if rendered else token
    return rendered


def id_format_variants(layout):
    """Yield the concrete field sequences a layout can appear as.

    The suffix field is optional, so a layout matches IDs both with and
    without it.

    Args:
        layout: An ID_FORMATS entry.

    Yields:
        Tuples of field names, longest first.
    """
    yield layout
    if "suffix" in layout:
        yield tuple(field for field in layout if field != "suffix")


def select_id_format(parts):
    """Pick the strain-ID layout selected by the COL version inside the ID.

    A layout is accepted only when the field in its "taxonomy_code" position
    parses as "<usage_id>.<col_version>" and that col_version is the index the
    layout is registered under. The version a name carries is therefore what
    decides how the name is read.

    Args:
        parts: Hyphen-separated fields of the strain ID.

    Returns:
        Tuple of (col_version, fields, taxonomy_match), where fields names the
        parts positionally and taxonomy_match is the TAXONOMY_RE match object.

    Raises:
        ValueError: If no registered layout fits the fields given, which
                    covers an unknown COL version, a wrong field count, and a
                    taxonomy code in the wrong position.
    """
    for col_version, layout in sorted(ID_FORMATS.items(), reverse=True):
        for fields in id_format_variants(layout):
            if len(parts) != len(fields):
                continue
            match = TAXONOMY_RE.match(parts[fields.index("taxonomy_code")])
            if match and int(match.group("col_version")) == col_version:
                return col_version, fields, match

    expected = " or ".join(describe_id_format(v) for v in sorted(ID_FORMATS))
    raise ValueError(
        f"strain ID {'-'.join(parts)!r} matches no known layout; expected "
        f"{expected}"
    )


def decode_strain_id(strain_id, session=None):
    """Break the strain ID into its components and resolve the taxonomy code.

    strain_id = <sequence>-<taxonomy_code>[-<suffix>]
    taxonomy_code = <usage_id>.<version>

    The layout is chosen from the version the taxonomy code carries, so the ID
    says how it should be read; see ID_FORMATS.

    Raises:
        ValueError: If the ID matches no registered layout or the suffix is
                    unrecognized. A sequence containing a hyphen, or an older
                    name that still carries a lab ID, will trip this.
    """
    parts = strain_id.split("-")
    col_version, fields, taxonomy_match = select_id_format(parts)
    values = dict(zip(fields, parts))

    if "suffix" in values:
        isolate_version, lab_passage = decode_isolate_suffix(values["suffix"])
    else:
        isolate_version, lab_passage = None, False

    usage_id = taxonomy_match.group("usage_id")
    dataset_key = COL_Version.get(col_version)

    scientific_name = resolve_scientific_name(dataset_key, usage_id, session=session)

    return {
        "taxonomy_code": values["taxonomy_code"],
        "col_dataset_key": dataset_key,
        "col_usage_id": usage_id,
        "scientific_name": scientific_name,
        "sequence": values["sequence"],
        "isolate_version": isolate_version,
        "lab_passage": lab_passage,
    }


def _vernacular_from_scientific(scientific_name):
    """Recover a vernacular name for a name whose host segment was omitted.

    Consults only the curated local host table, so this adds no network
    calls. Returns None when the taxon has no curated vernacular name.
    """
    if not scientific_name:
        return None
    try:
        return host_tools.get_canon_name(scientific_name)
    except KeyError:
        return None


def decode_strain_name(strain_name, session=None):
    """Decode a full influenza strain name into a metadata dictionary.

    Accepts both name shapes produced by the generator:

    * 5 segments — <type>/<host>/<location>/<strain_id>/<year>
    * 4 segments — <type>/<location>/<strain_id>/<year>, produced when the
      host segment was dropped because the host resolved to "Human" or could
      not be resolved to a vernacular name at all.

    For the 4-segment form the vernacular name is recovered from the taxon
    that the COL usage ID resolves to, so a human sample round-trips back to
    "Human". "host_segment_omitted" records which shape was decoded.

    For the 5-segment form, "_" in the host segment is read back as a space
    and the result is given in its host-table spelling, so both shapes agree
    ("red_junglefowl" and an omitted Gallus gallus segment both decode to
    "Red Junglefowl").

    "subtype" carries the parenthesised subtype from the year segment, or
    None when the name records none.

    Raises:
        ValueError: If the name has neither 4 nor 5 slash-separated segments,
                    or if the strain ID or year segment is malformed.
    """
    parts = strain_name.split("/")
    if len(parts) == 5:
        virus_type, host, location, strain_id, year_segment = parts
        host = host_tools.segment_to_vernacular(host)
        host_omitted = False
    elif len(parts) == 4:
        virus_type, location, strain_id, year_segment = parts
        host, host_omitted = None, True
    else:
        raise ValueError(
            f"expected 4 or 5 slash-separated segments, got {len(parts)}"
        )

    year, subtype = decode_year_segment(year_segment)

    sid = decode_strain_id(strain_id, session=session)

    if host_omitted:
        host = _vernacular_from_scientific(sid["scientific_name"])

    return {
        "virus_type": virus_type,
        "subtype": subtype,
        "host": {
            "vernacular_name": host,
            "scientific_name": sid["scientific_name"],
            "col_dataset_key": sid["col_dataset_key"],
            "col_usage_id": sid["col_usage_id"],
            "host_segment_omitted": host_omitted,
        },
        "location": decode_location(location),
        "date": {
            "year": year,
        },
        "sequence": sid["sequence"],
        "isolate_version": sid["isolate_version"],
        "lab_passage": sid["lab_passage"],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="strain-read",
        description=(
            "Decode an influenza isolate strain name into structured metadata. "
            "Strain name format: "
            "<type>/<host>/<location>/<strain_id>/<year>[(<subtype>)]"
        ),
    )
    parser.add_argument(
        "strain_name",
        metavar="STRAIN_NAME",
        help=(
            "The strain name to decode, e.g. "
            "'A/chicken/US-NY/002-3F72J.1-v2.L/2026(H5N1)'"
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
