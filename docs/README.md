# Influenza Strain Name Generator

## Overview

The purpose of this tool is to establish a standard for influenza strain names which is readable, concise, and data-rich.

The names this tool generates encode isolate metadata and are completely reversible so that a samples context will be preserved. Each strain name contains: host name, host taxonomic record, location (country and subdivision), collection year, a unique code for the original lab, and optionally an isolate version number, a lab passage marker, and the influenza subtype.

[Type]/[Vernacular Host]/[ISO 3166 Location]/[Catalogue of Life Taxonomy ID]-[Sequence]-[Lab Identifier]-[Suffix]/[Year]([Subtype])

The trailing suffix is optional. It is `v<N>` for a versioned isolate, `L` for a lab passage strain, or `v<N>.L` for both:

```
A/Chicken/US-VA/3F72J.1-01-MN.26A/2026        no version, not a passage strain
A/Chicken/US-VA/3F72J.1-01-MN.26A-v2/2026     version 2
A/Chicken/US-VA/3F72J.1-01-MN.26A-L/2026      lab passage strain
A/Chicken/US-VA/3F72J.1-01-MN.26A-v2.L/2026   version 2, lab passage strain
```

The trailing subtype is also optional, and is appended to the year in parentheses:

```
A/Chicken/US-VA/3F72J.1-01-MN.26A/2026        subtype not recorded
A/Chicken/US-VA/3F72J.1-01-MN.26A/2026(H5N1)  subtype H5N1
A/US-NY/6MB3T.1-042-MN.26A/2026(H3N2)         human sample, subtype H3N2
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

To generate a single name:

```bash
strain-gen single --virus-type "A" --host "Gallus gallus domesticus" --location "Virginia" --country "United States" --sequence "01" --lab-id "MN.26A" --date "2026-02-28"
```

To record an isolate version and/or a lab passage strain:

```bash
strain-gen single --virus-type "A" --host "Gallus gallus domesticus" --location "Virginia" --country "United States" --sequence "01" --lab-id "MN.26A" --date "2026-02-28" --isolate-version 2 --lab-passage
```

To record the influenza subtype:

```bash
strain-gen single --virus-type "A" --host "Gallus gallus domesticus" --location "Virginia" --country "United States" --sequence "01" --lab-id "MN.26A" --date "2026-02-28" --subtype "H5N1"
```

### Decoding Names

```bash
strain-read "A/Chicken/US-VA/3F72J.1-01-MN.26A-v2.L/2026(H5N1)"
```

Names produced by earlier versions of this tool, whose ID ended in a two-digit collection month, are not decodable by the current reader.

### Inputs

1. --virus-type

2. --host
   Latin Name of host species. Domestic and wild sub-species are differentiated. e.g. "Gallus gallus" != "Gallus gallus domesticus"

3. --location
   Name of the ISO 3166 subdivision where the sample was taken. e.g. "Virginia"

4. --country
   Name of the country where the sample was taken. e.g. "Mexico"

5. --sequence
   This is an internal lab ID. If a lab has ten samples from the same host type/location they might label them 1-10.

6. --lab-id
   Unique identifier for a lab. This is comprised of a two letter initial of the labs PI and a 3 character alphanumeric code.

7. --date
   Date in YYYY-MM-DD format. Only the year is recorded in the name.

8. --isolate-version (optional)
   Positive integer version number for this isolate. Encoded as "v<N>". e.g. 2 -> "v2"

9. --lab-passage (optional)
   Flag marking this as a lab passage strain. Encoded as "L".

10. --subtype (optional)
   Influenza subtype, appended to the year in parentheses. e.g. "H5N1" -> "/2026(H5N1)"
   The value is recorded verbatim and is not checked against a list of known subtypes, so
   novel reassortants are accepted. It may not contain "/", "(", ")", or whitespace, since
   any of those would make the name ambiguous to the reader.

In `file` mode these three are supplied as the optional CSV columns `isolate_version`,
`lab_passage`, and `subtype`; any or all may be omitted from the header. An empty
`isolate_version` cell means "unversioned", `lab_passage` accepts 1/true/t/yes/y, and an
empty `subtype` cell means the subtype was not recorded.
