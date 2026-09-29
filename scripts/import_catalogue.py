"""Import an authorised BIS metadata export into the local catalogue.

Usage:
    python scripts/import_catalogue.py path/to/authorised-bis-metadata.json

The input must be a JSON array. It is intentionally not a web scraper: the
operator must provide an authorised source/export with provenance fields.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from backend.catalogue import DEFAULT_CATALOGUE_PATH, import_catalogue


def main() -> int:
    parser = argparse.ArgumentParser(description="Import authorised BIS catalogue metadata")
    parser.add_argument("source", type=Path, help="Authorised JSON export")
    parser.add_argument("--destination", type=Path, default=DEFAULT_CATALOGUE_PATH)
    args = parser.parse_args()
    count = import_catalogue(args.source, args.destination)
    print(f"Imported {count} verified catalogue record(s) into {args.destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
