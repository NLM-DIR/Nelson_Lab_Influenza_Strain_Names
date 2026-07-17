"""
flu_strain_namer: Generates standardized influenza strain names.

Strain name format:
    <Virus Type>/<Host Species>/<Location>/<ID>/<Year>

ID format:
    [Country Code]-[Area Code]-[Month]-[Sequence]_[Lab Identifier]
"""

import argparse
import requests
import sys
from datetime import datetime

from name_gen.csv_handler import process_csv, REQUIRED_COLUMNS
from name_gen.tools import host_tools, location_tools, phone_code
from name_gen import package_config


def normalize_location(location: str, country: str) -> str:
    """Normalize a location to its conventional strain-name form.

    Args:
        location: City, state, or region.
        country:  Country for context.

    Returns:
        Normalized location string (e.g. "NewYork", "HongKong").
    """
    norm_country, subdivision_code = location_tools.get_country_and_subdivision(country, location)

    return norm_country, subdivision_code
    # raise NotImplementedError(f"Location normalization not yet implemented for: {location!r}, {country!r}")


def normalize_virus_type(virus_type: str) -> str:
    """TODO: Validate and normalize the influenza virus type.
    """
    return virus_type
    # raise NotImplementedError(f"Virus type normalization not yet implemented for: {virus_type!r}")


def make_strain_id_0(country, subdivision_string, month, year, sequence, lab_id) -> str:
    country_code = phone_code.get_country_code(country)
    area_code = location_tools.get_local_code(subdivision_string)

    isolate_id = f"{country_code}-{area_code}-{month}-{sequence}_{lab_id}"

    return isolate_id


def make_strain_id_1(host, month, sequence, lab_id) -> str:
    release = host_tools.resolve_latest_dataset_key()
    taxon_result = host_tools.match_species(host, release["dataset_key"])

    isolate_id = f"{taxon_result["usage_id"]}.{release["dataset_key"]}-{sequence}-{lab_id}-{month}"

    return isolate_id


# ---------------------------------------------------------------------------
# Strain name assembly
# ---------------------------------------------------------------------------
def assemble_strain_name(
    virus_type: str,
    host: str,
    location: str,
    country: str,
    sequence: str,
    lab_id: str,
    collection_date: datetime,
) -> str:
    """Assemble a standardized influenza strain name.

    Args:
        virus_type:       Influenza type/subtype (e.g. "H1N1", "H3N2", "B").
        host:             Host species (e.g. "Human", "Avian", "Swine").
        location:         Collection city/region.
        country:          Collection country (name or ISO code).
        sequence:         Lab sequence number for this isolate.
        lab_id:           Laboratory identifier suffix.
        collection_date:  Date the sample was collected.

    Returns:
        Formatted strain name string, e.g.:
        "A/Duck/New York/1-212-03-042_NYSDOH/2025"
    """

    # FORMAT 0:
    # [Type]/[Vernacular Host]/[Common Location]/[Phone CC]-[Local Code]-[Month]-[Lab Identifier]/[Year]

    # FORMAT 1:
    # [Type]/[Vernacular Host]/[ISO Subdivision]/[Taxon ID]-[Lab Identifier]-[Month]/[Year]

    norm_type = normalize_virus_type(virus_type)
    norm_host = None
    with requests.Session() as s:
        norm_host = host_tools.scientific_to_vernacular(host, session=s)
    common_name, subdivision_string = normalize_location(location, country)
    month = f"{collection_date.month:02d}"
    year = str(collection_date.year)

    match package_config["format"]:
        case 1:
            strain_id = make_strain_id_1(host, month, sequence, lab_id)
            strain_location = subdivision_string
        case _:
            strain_id = make_strain_id_0(country, subdivision_string, month, year, sequence, lab_id)
            strain_location = common_name

    # Build the slash-delimited components; drop host segment if human
    if norm_host.lower() == "human" or not norm_host:
        components = [norm_type, strain_location, strain_id, year]
    else:
        components = [norm_type, norm_host, strain_location, strain_id, year]
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
        help='Host species, e.g. "Avian", "Swine". '
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
        "--lab-id", "-b",
        required=True,
        metavar="LAB_ID",
        help="Laboratory identifier appended to the isolate ID (e.g. NYSDOH).",
    )
    single.add_argument(
        "--date", "-d",
        required=True,
        metavar="YYYY-MM-DD",
        help="Sample collection date in YYYY-MM-DD format.",
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
        help="Path to write the updated CSV. Defaults to overwriting the input file.",
    )
    file_mode.add_argument(
        "--strain-column",
        default="strain_name",
        metavar="NAME",
        help="Name of the new column to hold the generated strain names.",
    )

    return parser.parse_args()


def run_single(args: argparse.Namespace) -> None:
    if not args.human and not args.host:
        raise SystemExit("Error: --host is required unless --human is given.")

    host = "Human" if args.human else args.host

    try:
        collection_date = datetime.strptime(args.date, "%Y-%m-%d")
    except ValueError:
        raise SystemExit(f"Error: --date must be in YYYY-MM-DD format, got: {args.date!r}")

    strain_name = assemble_strain_name( 
        virus_type=args.virus_type,
        host=host,
        location=args.location,
        country=args.country,
        sequence=args.sequence,
        lab_id=args.lab_id,
        collection_date=collection_date,
    )

    print(strain_name)


def run_file(args: argparse.Namespace) -> None:
    output_path = args.output or args.input
    try:
        n_ok, errors = process_csv(
            input_path=args.input,
            output_path=output_path,
            strain_column=args.strain_column,
            assemble_fn=assemble_strain_name,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(f"Error: {exc}")

    print(f"Wrote {n_ok} strain name(s) to {output_path}", file=sys.stderr)
    if errors:
        print(f"Skipped {len(errors)} row(s):", file=sys.stderr)
        for row_num, msg in errors:
            print(f"  Row {row_num}: {msg}", file=sys.stderr)


def main() -> None:
    args = parse_args()

    if args.mode == "single":
        run_single(args)
    elif args.mode == "file":
        run_file(args)


if __name__ == "__main__":
    main()
