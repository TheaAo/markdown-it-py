from __future__ import annotations

import argparse
import csv
from pathlib import Path
import sys
from typing import Any, Sequence

try:
    from scripts.metric_collection.mutation_common import (
        REVIEW_STATUSES,
        load_catalog,
        write_json,
    )
except ModuleNotFoundError:  # pragma: no cover
    from mutation_common import (  # type: ignore[no-redef]
        REVIEW_STATUSES,
        load_catalog,
        write_json,
    )


def apply_reviews(catalog_path: Path, reviews_path: Path) -> dict[str, Any]:
    catalog = load_catalog(catalog_path)
    by_id = {item["mutant_id"]: item for item in catalog["mutants"]}
    with reviews_path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    seen: set[str] = set()
    for row in rows:
        mutant_id = row.get("mutant_id", "")
        review_status = row.get("review_status", "")
        if mutant_id not in by_id:
            raise ValueError(f"review contains unknown mutant ID: {mutant_id}")
        if mutant_id in seen:
            raise ValueError(f"review contains duplicate mutant ID: {mutant_id}")
        if review_status not in REVIEW_STATUSES:
            raise ValueError(f"invalid review status for {mutant_id}: {review_status}")
        by_id[mutant_id]["review_status"] = review_status
        by_id[mutant_id]["review_notes"] = row.get("review_notes", "")
        seen.add(mutant_id)
    write_json(catalog_path, catalog)
    return catalog


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Apply reviewed equivalent-mutant decisions to a catalog."
    )
    parser.add_argument("catalog", type=Path)
    parser.add_argument("reviews", type=Path)
    args = parser.parse_args(argv)
    try:
        catalog = apply_reviews(args.catalog.resolve(), args.reviews.resolve())
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"Updated {len(catalog['mutants'])} catalog mutants")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
