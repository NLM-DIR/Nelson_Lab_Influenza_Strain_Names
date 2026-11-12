# Influenza Strain Name Generator

## Overview

The purpose of this tool is to establish a standard for influenza strain names which is readable, concise, and data-rich.

The names this tool generates encode isolate metadata and are completely reversible so that a samples context will be preserved. Each strain name contains: host name, whether the host was domestic or wild, host taxonomic record, location (country and subdivision), collection year, a lab sequence number, and optionally a unique laboratory identifier (ULI), an isolate version number, a lab passage marker, a reverse genetics marker, and the influenza subtype.

[Type]/[Vernacular Host]/[ISO 3166 Location]/[Sequence]-[Host Origin].[Catalogue of Life Taxonomy ID]-[ULI]-[Suffix]/[Year]([Subtype])

The host origin leads the taxonomy ID: `d` for a domestic host, `w` for a wild one. It is required for every sample except lab passage (`L`) and reverse genetics (`RG`) strains, which may leave it out, and human samples, which never carry it:

```
A/chicken/US-VA/01-d.3F72J.1/2026        domestic host
A/mallard/US-VA/01-w.4XYZ8.1/2026        wild host
A/chicken/US-VA/01-3F72J.1-L/2026        lab passage strain, origin left out
A/chicken/US-VA/01-d.3F72J.1-L/2026      lab passage strain, origin given
A/US-NY/042-6MB3T.1/2026                 human sample, no origin
```

The trailing suffix is optional. It joins, in this order and separated by `.`, any of `v<N>` for a versioned isolate, `L` for a lab passage strain, and `RG` for a reverse genetics strain:

```
A/chicken/US-VA/01-d.3F72J.1/2026          no version, not a passage strain
A/chicken/US-VA/01-d.3F72J.1-v2/2026       version 2
A/chicken/US-VA/01-3F72J.1-L/2026          lab passage strain
A/chicken/US-VA/01-3F72J.1-v2.L/2026       version 2, lab passage strain
A/chicken/US-VA/01-3F72J.1-RG/2026         reverse genetics strain
A/chicken/US-VA/01-d.3F72J.1-v2.L.RG/2026  all three, origin given
```

The ULI is optional. It is a 5-character code of letters and digits, written in uppercase, placed after the taxonomy ID and before any suffix:

```
A/US-CA/55-6MB3T.1-AB12C/2020          ULI AB12C
A/US-CA/55-6MB3T.1-AB12C-v2.L/2020     ULI AB12C, version 2, lab passage strain
```

The trailing subtype is also optional, and is appended to the year in parentheses:

```
A/chicken/US-VA/01-d.3F72J.1/2026        subtype not recorded
A/chicken/US-VA/01-d.3F72J.1/2026(H5N1)  subtype H5N1
A/US-NY/042-6MB3T.1/2026(H3N2)         human sample, subtype H3N2
```

It is omitted rather than left blank when unknown, which is the expected case for influenza B, whose lineages are not H/N subtypes.

## Usage

### Setup

To use this tool first install it as a package and install the requirements. We strongly recommend you use a [virtual environment](https://www.w3schools.com/python/python_virtualenv.asp).

```bash
pip install .
```

### Generating Names

To generate names from a file:

```bash
strain-gen file --input .\test_data\example.csv --output ./out.csv
```

The input file is never modified. Without `--output`, names are written to
`<input>_strain_names.csv` next to the input, and the run stops if that file already exists.
Every input row appears in the output. A row that can't be named gets an empty `strain_name` and
the reason in an `error` column, and the command exits with status 1.

To generate a single name:

```bash
strain-gen single --virus-type "A" --host "Gallus gallus domesticus" --location "Virginia" --country "United States" --sequence "01" --year "2026" --host-origin domestic
```

To record an isolate version and/or a lab passage strain:

```bash
strain-gen single --virus-type "A" --host "Gallus gallus domesticus" --location "Virginia" --country "United States" --sequence "01" --year "2026" --isolate-version 2 --lab-passage
```

To record the influenza subtype:

```bash
strain-gen single --virus-type "A" --host "Gallus gallus domesticus" --location "Virginia" --country "United States" --sequence "01" --year "2026" --host-origin d --subtype "H5N1"
```

### Decoding Names

```bash
strain-read "A/chicken/US-VA/01-d.3F72J.1-v2.L/2026(H5N1)"
```

The output reports the host origin as `host.origin`: `"domestic"`, `"wild"`, or `null` when the name carries none. Names generated before the host origin was introduced still decode, with `host.origin` set to `null`.

The reader picks the ID layout from the Catalogue of Life version number the name itself carries, so names stay readable across future releases. Names produced by earlier versions of this tool are not decodable by the current reader: neither those whose ID ended in a two-digit collection month, nor those whose ID led with the taxonomy code, nor those that carry a lab identifier (e.g. `01-MN.26A-3F72J.1`).

### Inputs

1. --virus-type

2. --host
   Scientific or common name of the host. Domestic and wild sub-species are differentiated. e.g. "Gallus gallus" != "Gallus gallus domesticus"
   When the species is unknown, give a common name or a host group instead: "duck", "gull", "bird", "seal".
   The name then records the group ("A/duck/...") and the Catalogue of Life ID of the group's taxon (Anatidae for duck).
   A common name that isn't in the curated table is placed by its last word ("baikal teal" -> duck), and a warning says so.
   Give the scientific name whenever you know it, so the name records the exact species.
   The full list of species and groups is in `src/strain_generator/data/host_map.json`.

3. --location
   Name or code of the ISO 3166-2 subdivision where the sample was taken. e.g. "Virginia", "VA", or "US-VA".
   Names are matched as pycountry lists them, which is often the local-language form ("Bayern", not "Bavaria").
   Unmatched or ambiguous locations (e.g. "Carolina") are rejected. Leave blank if unknown.

4. --country
   Name or ISO code of the country where the sample was taken. e.g. "Mexico", "MX", or "U.S.A."

5. --sequence
   This is an internal lab ID. If a lab has ten samples from the same host type/location they might label them 1-10.

6. --year
   4-digit year the sample was collected, e.g. "2026". Full dates are rejected.
   In file mode, use a `year` column.

7. --isolate-version (optional)
   Positive integer version number for this isolate. Encoded as "v<N>". e.g. 2 -> "v2"

8. --lab-passage (optional)
   Flag marking this as a lab passage strain. Encoded as "L".

   --reverse-genetics, -rg (optional)
   Flag marking this as a reverse genetics strain. Encoded as "RG".

9. --subtype (optional)
   Influenza subtype, appended to the year in parentheses. e.g. "H5N1" -> "/2026(H5N1)"
   The value is recorded verbatim and is not checked against a list of known subtypes, so
   novel reassortants are accepted. It may not contain "/", "(", ")", or whitespace, since
   any of those would make the name ambiguous to the reader.

10. --uli (optional)
   Unique laboratory identifier: exactly 5 letters or digits. Lowercase input is uppercased, e.g. "ab12c" -> "-AB12C".
   In file mode, use a `uli` column.

11. --host-origin, -H
   Whether the host was domestic (`d` or `domestic`) or wild (`w` or `wild`), case-insensitive. Written before the taxonomy ID, e.g. "01-d.3F72J.1".
   Required unless the sample is human or the strain is a lab passage (`--lab-passage`) or reverse genetics (`--reverse-genetics`) strain. Not allowed for human samples.
   In file mode, use a `host_origin` column.

In `file` mode these are supplied as the optional CSV columns `isolate_version`,
`lab_passage`, `reverse_genetics`, `subtype`, `uli` and `host_origin`; any or all may be
omitted from the header. An empty `isolate_version` cell means "unversioned", `lab_passage` and
`reverse_genetics` accept 1/true/t/yes/y, and an empty `subtype` cell means the subtype was
not recorded. A row with an empty or missing `host_origin` fails (with the reason in the
`error` column) unless it is a human, lab passage or reverse genetics sample.
