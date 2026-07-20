# Influenza Strain Name Generator

## Overview

The purpose of this tool is to establish a standard for influenza strain names which is readable, concise, and data-rich.

The names this tool generates encodes isolate metadata and is completely reversible so that a samples context will be preserved. Each strain name contains: host name, host taxonomic record, location (country and subdivision), collection month, collection year, and a unique code for the original lab.

[Type]/[Vernacular Host]/[ISO 3166 Location]/[Catalogue of Life Taxonomy ID]-[Lab Identifier]-[Month]/[Year]

## Usage

### Setup

To use this tool first install it as a package and install the requirements. We recommend you use a [virtual environment](https://www.w3schools.com/python/python_virtualenv.asp).

```bash
pip install .
pip install -r requirements.txt
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

### Decoding Names

```bash
strain-read 'A/Domestic Chicken/US-NY/3F72J.1-002_MN_26A-06/2026'
```

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
   Date in YYYY-MM-DD format.
