# Influenza Strain Name Generator

## Overview

The purpose of this tool is to establish a standard for influenza strain names which is readable, concise, and data-rich.

The names this tool generates encodes isolate metadata and is completely reversible so that a samples context will be preserved. Each strain name contains: host name, host taxonomic record, location (country and subdivision), collection month, collection year, and a unique code for the original lab.

[Type]/[Vernacular Host]/[ISO 3166 Location]/[Catalogue of Life Taxonomy ID][Sample Number][Lab ID][Month]/[Year]

## Usage

### Inputs

### Generating Names

To use this tool first install it as a package.

```bash
pip install .
```

To generate names from a file:

```bash
strain-gen file --input .\test_data\example.csv --output ./out.csv
```

To generate a single name:

```bash
strain-gen single --virus-type "A" --host "Gallus gallus" --location "Virginia" --country "United States" --sequence "01" --lab-id "MN.26A" --date "2026-02-28"
```

### Decoding Names

```bash
strain-read 'A/Domestic Chicken/US-NY/3F72J.1-002_MN_26A-06/2026'
```
