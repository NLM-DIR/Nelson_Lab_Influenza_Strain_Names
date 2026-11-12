"""
strain_generator.main: Generates standardized influenza strain names.

Strain name format:
    <Virus Type>/<Vernacular Host>/<Location>/<ID>/<Year>[(<Subtype>)]

The host segment is omitted for human samples. The year carries an optional
parenthesised subtype, e.g. "2026(H5N1)".

ID format:
    [Sequence]-[Host Origin.][COL Usage ID].[COL Version][-ULI][-Suffix]

The host origin is "d" (domestic) or "w" (wild). It is required for every
non-human sample except lab passage and reverse genetics strains, which may
leave it out; human samples never carry it.

The ULI (unique laboratory identifier) is an optional 5-character uppercase
alphanumeric code. The suffix is optional and joins, in this order, any of
"v<N>" (isolate version), "L" (lab passage strain) and "RG" (reverse
genetics) with ".", e.g. "v2", "L.RG", "v2.L.RG".
"""

import argparse
import requests
import sys
from pathlib import Path
from typing import Optional

from strain_generator.csv_handler import process_csv, REQUIRED_COLUMNS
from strain_generator.tools import host_tools, location_tools
from strain_generator.tools.utils import (
    HUMAN_SCIENTIFIC_NAME, parse_year, space_to_underscore,
)
from strain_generator import package_config


def normalize_location(location: str, country: str) -> str:
    """Normalize a location to its conventional strain-name form.

    Args:
        location: ISO 3166 subdivision name (state, province, or region).
        country:  Country for context.

    Returns:
        Tuple of (country display name, subdivision code), e.g.
        ("United States", "US-VA").
    """
    if location is None:
        raise ValueError("You must include a host location (state/province).")
    if country is None:
        raise ValueError("You must include host country.")

    norm_country, subdivision_code = location_tools.get_country_and_subdivision(country, location)
    return norm_country, subdivision_code
    # raise NotImplementedError(f"Location normalization not yet implemented for: {location!r}, {country!r}")


def normalize_virus_type(virus_type: str) -> str:
    """
    Return the influenza virus type.
    """

    normalized_type = virus_type.upper().strip()

    if normalized_type not in ("A", "B", "C", "D"):
        raise ValueError(f"{virus_type} not valid influenza type.\nMust be one of: `A`, `B`, `C`, `D`")
    
    return virus_type


def normalize_subtype(subtype: Optional[str]) -> Optional[str]:
    """Validate the influenza subtype and strip surrounding whitespace.

    The subtype is recorded verbatim and is deliberately not checked against a
    list of known subtypes, so novel reassortants and provisional designations
    are accepted. Only characters that would make a name ambiguous to the
    reader are rejected.

    Args:
        subtype: Subtype string such as "H5N1", or None when not recorded.

    Returns:
        The stripped subtype, or None when nothing was supplied.

    Raises:
        ValueError: If the subtype contains "/", "(", ")", or whitespace.
    """
    if subtype is None:
        return None

    norm = subtype.strip()
    if not norm:
        return None

    bad = sorted({c for c in norm if c in "/()" or c.isspace()})
    if bad:
        raise ValueError(
            f"subtype {subtype!r} contains disallowed character(s) "
            f"{' '.join(repr(c) for c in bad)}; '/', '(', ')' and whitespace "
            f"would make the strain name ambiguous to the reader"
        )
    return norm


def normalize_uli(uli: Optional[str]) -> Optional[str]:
    """Validate a unique laboratory identifier (ULI) and uppercase it.

    Uppercasing keeps a ULI distinct from the lowercase isolate-version
    suffix ("v1234"), which is how the reader tells the two apart.

    Args:
        uli: Five-character alphanumeric code, or None when not recorded.

    Returns:
        The uppercased ULI, or None when nothing was supplied.

    Raises:
        ValueError: If the ULI is not exactly 5 ASCII letters or digits.
    """
    if uli is None:
        return None

    norm = uli.strip().upper()
    if not norm:
        return None

    if len(norm) != 5 or not (norm.isascii() and norm.isalnum()):
        raise ValueError(
            f"ULI {uli!r} must be exactly 5 letters or digits, e.g. 'AB12C'"
        )
    return norm


# Accepted spellings of each host origin, mapped to the letter written in the ID.
HOST_ORIGINS = {"d": "d", "domestic": "d", "w": "w", "wild": "w"}


def normalize_host_origin(origin: Optional[str]) -> Optional[str]:
    """Validate a host origin and reduce it to its one-letter code.

    Args:
        origin: "d"/"domestic" or "w"/"wild" in any case, or None when not
                recorded.

    Returns:
        "d" or "w", or None when nothing was supplied.

    Raises:
        ValueError: If the origin is not one of the accepted spellings.
    """
    if origin is None:
        return None

    norm = origin.strip().lower()
    if not norm:
        return None

    if norm not in HOST_ORIGINS:
        raise ValueError(
            f"host origin {origin!r} must be 'd'/'domestic' or 'w'/'wild'"
        )
    return HOST_ORIGINS[norm]


def check_host_origin(
    host_origin: Optional[str],
    is_human: bool,
    lab_passage: bool,
    reverse_genetics: bool,
) -> None:
    """Enforce when a host origin must, or must not, be given.

    Args:
        host_origin:      Normalized origin ("d", "w") or None.
        is_human:         Whether the host resolved to a human. Decided after
                          host resolution, since host_map mode also accepts
                          the common name "human".
        lab_passage:      Whether this is a lab passage strain.
        reverse_genetics: Whether this is a reverse genetics strain.

    Raises:
        ValueError: If a human sample carries an origin, or a non-human
                    sample that is neither a lab passage nor a reverse
                    genetics strain lacks one.
    """
    if is_human:
        if host_origin:
            raise ValueError(
                "host origin (domestic or wild) does not apply to human samples"
            )
        return
    if not host_origin and not (lab_passage or reverse_genetics):
        raise ValueError(
            "host origin (domestic or wild) is required unless the strain is "
            "a lab passage or reverse genetics strain"
        )


@space_to_underscore  # Multi-word hosts become e.g. "domestic_turkey".
def normalize_host(scientific_host):
    """Convert a scientific host name to its host-segment form.

    The vernacular name is lowercased and, via the decorator, its spaces are
    written as "_". The reader reverses this with
    host_tools.segment_to_vernacular.

    Raises:
        ValueError: If the host has no vernacular name, or the vernacular
                    contains "_" (which the reader would turn into a space)
                    or "/" (the segment delimiter).
    """
    with requests.Session() as s:
        norm_host = host_tools.scientific_to_vernacular(scientific_host, session=s)
    if not norm_host:
        raise ValueError(f"{scientific_host} is not a valid host name.")
    return host_label_to_segment(norm_host, scientific_host)


@space_to_underscore
def host_label_to_segment(label, host):
    """Lowercase a vernacular label for the host segment.

    Args:
        label: Vernacular name to write ("Domestic Turkey", "Duck").
        host:  The host as given, for the error message.

    Raises:
        ValueError: If the label contains "_" (which the reader would turn
                    into a space) or "/" (the segment delimiter).
    """
    bad = sorted({c for c in label if c in "_/"})
    if bad:
        raise ValueError(
            f"vernacular name {label!r} for host {host!r} contains "
            f"disallowed character(s) {' '.join(repr(c) for c in bad)}; it can't "
            f"be written into the host segment unambiguously"
        )
    return label.lower()


def resolve_host_segment(host):
    """Resolve a host to its segment form plus the taxon its ID is minted from.

    `package.yaml`'s `host_resolver` picks the path. "host_map" accepts a
    scientific or common name and resolves it through data/host_map.json
    (host_tools.resolve_host). "legacy" -- also the default when the key is
    absent -- is the original scientific-name-only path through
    data/host_name.json, kept so the change can be rolled back.

    Returns:
        Tuple of (host segment, name to match in COL, usage ID or None).
    """
    if package_config.get("host_resolver", "legacy") == "host_map":
        with requests.Session() as s:
            resolved = host_tools.resolve_host(
                host, package_config["COL_dataset_key"], session=s
            )
        segment = host_label_to_segment(resolved.label, host)
        return segment, resolved.col_name, resolved.usage_id
    return normalize_host(host), host, None


def make_isolate_suffix(
    isolate_version: Optional[int] = None,
    lab_passage: bool = False,
    reverse_genetics: bool = False,
) -> str:
    """Build the optional trailing segment of the strain ID.

    Args:
        isolate_version:  Isolate version number, or None if unversioned.
        lab_passage:      Whether this is a lab passage strain.
        reverse_genetics: Whether this strain was made by reverse genetics.

    Returns:
        "v2", "L", "RG", "v2.L.RG", etc., or "" when no input is given.
    """
    parts = []
    if isolate_version is not None:
        parts.append(f"v{isolate_version}")
    if lab_passage:
        parts.append("L")
    if reverse_genetics:
        parts.append("RG")

    return ".".join(parts)


def make_strain_id(
    host,
    sequence,
    isolate_version: Optional[int] = None,
    lab_passage: bool = False,
    usage_id: Optional[str] = None,
    uli: Optional[str] = None,
    reverse_genetics: bool = False,
    host_origin: Optional[str] = None,
) -> str:
    """Build the ID segment of a strain name.

    Resolves the host against the pinned COL release, then combines it with
    the sequence number, the optional ULI, and the optional suffix.

    Args:
        usage_id: COL usage ID already matched for the host, which skips the
                  COL lookup.
        uli:      Normalized unique laboratory identifier, or None.
        reverse_genetics: Whether to append "RG" to the suffix.
        host_origin: Normalized host origin ("d" or "w"), prefixed to the
                  taxonomy code, or None to leave it out.

    Returns:
        e.g. "002-3F72J.1", "002-d.3F72J.1", or "002-w.3F72J.1-AB12C-v2.L"
        when every optional input is supplied.
    """
    if usage_id is None:
        # release = host_tools.resolve_latest_dataset_key()
        # taxon_result = host_tools.match_species(host, release["dataset_key"])
        taxon_result = host_tools.match_species(host, package_config["COL_dataset_key"])
        if not taxon_result:
            raise ValueError(
                f"could not resolve host {host!r} to a taxon in COL dataset "
                f"{package_config['COL_dataset_key']}; check the spelling of the "
                f"scientific name"
            )
        usage_id = taxon_result["usage_id"]

    taxonomy_code = f"{usage_id}.{package_config['COL_version']}"
    if host_origin:
        taxonomy_code = f"{host_origin}.{taxonomy_code}"
    if uli:
        taxonomy_code = f"{taxonomy_code}-{uli}"
    suffix = ""
    if isolate_version or lab_passage or reverse_genetics:
        suffix = "-" + make_isolate_suffix(
            isolate_version, lab_passage, reverse_genetics
        )

    return f"{sequence}-{taxonomy_code}{suffix}"


# ---------------------------------------------------------------------------
# Strain name assembly
# ---------------------------------------------------------------------------

def assemble_strain_name(
    virus_type: str,
    host: str,
    location: str,
    country: str,
    sequence: str,
    year: int,
    isolate_version: Optional[int] = None,
    lab_passage: bool = False,
    subtype: Optional[str] = None,
    uli: Optional[str] = None,
    reverse_genetics: bool = False,
    host_origin: Optional[str] = None,
) -> str:
    """Assemble a standardized influenza strain name.

    Args:
        virus_type:       Influenza type/subtype (e.g. "H1N1", "H3N2", "B").
        host:             Host scientific name (e.g. "Gallus gallus domesticus"),
                          or, with host_resolver: host_map, a common name
                          ("duck"). See resolve_host_segment.
        location:         Collection subdivision (state, province, or region).
        country:          Collection country (name or ISO code).
        sequence:         Lab sequence number for this isolate.
        year:             4-digit year the sample was collected.
        isolate_version:  Optional isolate version number, encoded as "v<N>".
        lab_passage:      Whether this is a lab passage strain, encoded as "L".
        subtype:          Optional influenza subtype, appended to the year in
                          parentheses, e.g. "2026(H5N1)". Omitted entirely when
                          not supplied, which is the expected case for type B.
        uli:              Optional 5-character unique laboratory identifier,
                          uppercased and placed after the taxonomy code, e.g.
                          "15-d.3F72J.1-AB12C-v2".
        reverse_genetics: Whether this strain was made by reverse genetics,
                          encoded as "RG".
        host_origin:      "d"/"domestic" or "w"/"wild", prefixed to the
                          taxonomy code, e.g. "15-d.3F72J.1". Required for
                          non-human hosts unless lab_passage or
                          reverse_genetics is set; not allowed for humans.

    Returns:
        Formatted strain name string, e.g.:
        "A/chicken/US-VA/15-d.3F72J.1/2026(H5N1)"

        Multi-word hosts are lowercased with spaces written as "_", e.g.
        "A/domestic_turkey/...". The host segment is dropped when the host resolves to "Human" or
        cannot be resolved to a vernacular name.

    Raises:
        ValueError: If the subtype contains a character that would make the
                    name ambiguous (see normalize_subtype), or the ULI is
                    malformed (see normalize_uli), or the host origin is
                    malformed, missing or not allowed (see
                    check_host_origin).
    """

    norm_type = normalize_virus_type(virus_type)
    norm_subtype = normalize_subtype(subtype)
    norm_uli = normalize_uli(uli)
    norm_origin = normalize_host_origin(host_origin)
    norm_host, col_name, usage_id = resolve_host_segment(host)
    is_human = (
        not norm_host
        or norm_host.lower() == "human"
        or col_name == HUMAN_SCIENTIFIC_NAME
    )
    check_host_origin(norm_origin, is_human, lab_passage, reverse_genetics)

    _, subdivision_string = normalize_location(location, country)
    
    year_segment = f"{year:04d}"
    if norm_subtype:
        year_segment = f"{year_segment}({norm_subtype})"

    match package_config["name_format"]:
        case _:
            strain_id = make_strain_id(
                col_name, sequence, isolate_version, lab_passage, usage_id,
                norm_uli, reverse_genetics, norm_origin,
            )
            strain_location = subdivision_string

    # Build the slash-delimited components; drop host segment if human
    if is_human:
        components = [norm_type, strain_location, strain_id, year_segment]
    else:
        components = [norm_type, norm_host, strain_location, strain_id, year_segment]
    components = [c for c in components if c]  # remove empty strings

    return "/".join(components)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="strain-gen",
        description="Generate standardized influenza strain names from sample metadata.",
    )

    subparsers = parser.add_subparsers(
        dest="mode",
        required=True,
        metavar="{single,file}",
        help="Generation mode.",
    )

    # ----- single mode -----------------------------------------------------
    single = subparsers.add_parser(
        "single",
        help="Generate a single strain name from command-line metadata.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    single.add_argument(
        "--virus-type", "-v",
        required=True,
        metavar="TYPE",
        help="Influenza type/subtype, e.g. H1N1, H3N2, B.",
    )
    single.add_argument(
        "--host", "-s",
        metavar="SPECIES",
        help='Host as a scientific or common name, e.g. "Anas platyrhynchos", '
             '"cinnamon teal", "duck". Common names need host_resolver: host_map. '
             "Required unless --human is given.",
    )
    single.add_argument(
        "--human",
        action="store_true",
        help="Mark this as a human sample (no --host required).",
    )
    single.add_argument(
        "--location", "-l",
        required=True,
        metavar="LOCATION",
        help="City or region where the sample was collected.",
    )
    single.add_argument(
        "--country", "-c",
        required=True,
        metavar="COUNTRY",
        help="Country where the sample was collected (name or ISO 3166 code).",
    )
    single.add_argument(
        "--sequence", "-n",
        required=True,
        metavar="SEQ",
        help="Lab sequence number for this isolate (e.g. 042).",
    )
    single.add_argument(
        "--year", "-y",
        required=True,
        metavar="YYYY",
        help="4-digit year the sample was collected (e.g. 2026).",
    )
    single.add_argument(
        "--isolate-version", "-V",
        type=int,
        metavar="N",
        help="Optional isolate version number, appended to the ID as 'v<N>'.",
    )
    single.add_argument(
        "--lab-passage", "-L",
        action="store_true",
        help="Mark this as a lab passage strain, appended to the ID as 'L'.",
    )
    single.add_argument(
        "--reverse-genetics", "-rg",
        action="store_true",
        help="Mark this as a reverse genetics strain, appended to the ID as "
             "'RG'.",
    )
    single.add_argument(
        "--host-origin", "-H",
        metavar="{d,w}",
        help="Whether the host was domestic ('d'/'domestic') or wild "
             "('w'/'wild'), prefixed to the taxonomy code, e.g. "
             "'01-d.3F72J.1'. Required unless --human, --lab-passage or "
             "--reverse-genetics is given; not allowed with --human.",
    )
    single.add_argument(
        "--subtype", "-t",
        metavar="SUBTYPE",
        help="Optional influenza subtype, appended to the year in parentheses "
             "e.g. 'H5N1' -> '/2026(H5N1)'. Recorded verbatim; may not contain "
             "'/', '(', ')', or whitespace.",
    )
    single.add_argument(
        "--uli", "-u",
        metavar="ULI",
        help="Optional unique laboratory identifier: exactly 5 letters or "
             "digits, uppercased and placed after the taxonomy code, e.g. "
             "'ab12c' -> '01-d.3F72J.1-AB12C'.",
    )

    # ----- file mode -------------------------------------------------------
    file_mode = subparsers.add_parser(
        "file",
        help="Generate strain names for every row of a CSV file.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    file_mode.add_argument(
        "--input", "-i",
        required=True,
        metavar="INPUT_CSV",
        help=(
            "Path to the input CSV. Must contain the columns: "
            + ", ".join(REQUIRED_COLUMNS) + "."
        ),
    )
    file_mode.add_argument(
        "--output", "-o",
        metavar="OUTPUT_CSV",
        help="Path to write the updated CSV. Defaults to <input>_strain_names.csv "
             "beside the input; the input file is never overwritten.",
    )
    file_mode.add_argument(
        "--strain-column",
        default="strain_name",
        metavar="NAME",
        help="Name of the new column to hold the generated strain names.",
    )
    file_mode.add_argument(
        "--error-column",
        default="error",
        metavar="NAME",
        help="Name of the new column to hold the reason a row could not be named.",
    )

    return parser.parse_args()


def run_single(args: argparse.Namespace) -> None:
    if not args.human and not args.host:
        raise SystemExit("Error: --host is required unless --human is given.")

    host = HUMAN_SCIENTIFIC_NAME if args.human else args.host

    if args.isolate_version is not None and args.isolate_version < 1:
        raise SystemExit(
            f"Error: --isolate-version must be a positive integer, got: "
            f"{args.isolate_version}"
        )

    try:
        year = parse_year(args.year, "--year")
    except ValueError as exc:
        raise SystemExit(f"Error: {exc}")

    try:
        strain_name = assemble_strain_name(
            virus_type=args.virus_type,
            host=host,
            location=args.location,
            country=args.country,
            sequence=args.sequence,
            year=year,
            isolate_version=args.isolate_version,
            lab_passage=args.lab_passage,
            reverse_genetics=args.reverse_genetics,
            subtype=args.subtype,
            uli=args.uli,
            host_origin=args.host_origin,
        )
    except ValueError as exc:
        # Raised by normalize_subtype/normalize_uli/normalize_host_origin for
        # a malformed value, by check_host_origin for a missing or disallowed
        # host origin, by
        # make_strain_id when the host has no match in the pinned COL release,
        # and by location_tools for an unmatched country or an unmatched or
        # ambiguous subdivision.
        raise SystemExit(f"Error: {exc}")
    except requests.RequestException as exc:
        raise SystemExit(
            f"Error: could not reach an external lookup service: {exc}"
        )

    print(strain_name)


def default_output_path(input_path: str) -> str:
    """Return the output path used when --output is omitted.

    "data/samples.csv" -> "data/samples_strain_names.csv"
    """
    path = Path(input_path)
    return str(path.with_name(f"{path.stem}_strain_names.csv"))


def run_file(args: argparse.Namespace) -> None:
    output_path = args.output
    if not output_path:
        output_path = default_output_path(args.input)
        if Path(output_path).exists():
            raise SystemExit(
                f"Error: {output_path} already exists; pass --output to choose "
                f"another path"
            )

    try:
        n_ok, errors = process_csv(
            input_path=args.input,
            output_path=output_path,
            strain_column=args.strain_column,
            assemble_fn=assemble_strain_name,
            error_column=args.error_column,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(f"Error: {exc}")

    n_rows = n_ok + len(errors)
    print(f"Wrote {n_rows} row(s) to {output_path} ({n_ok} named)", file=sys.stderr)
    if errors:
        print(
            f"Failed to name {len(errors)} row(s); see the "
            f"{args.error_column!r} column:",
            file=sys.stderr,
        )
        for row_num, msg in errors:
            print(f"  Row {row_num}: {msg}", file=sys.stderr)
        raise SystemExit(1)


def main() -> None:
    args = parse_args()

    if args.mode == "single":
        run_single(args)
    elif args.mode == "file":
        run_file(args)


if __name__ == "__main__":
    main()
