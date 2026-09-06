"""Strictly validate completed schema-mapping annotation artifacts."""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.schema.canonical import CanonicalSchema
from src.schema.gold_mapping import compare_annotators, load_gold_annotations


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--annotations", type=Path, required=True)
    parser.add_argument("--compare", type=Path)
    args = parser.parse_args()
    schema = CanonicalSchema.from_template()
    primary = load_gold_annotations(args.annotations, schema=schema)
    counts = Counter(item.gold_status.value for item in primary.annotations)
    eligible = sum(item.calibration_eligible for item in primary.annotations)
    print(f"valid annotations: {len(primary.annotations)}")
    print(f"status counts: {dict(sorted(counts.items()))}")
    print(f"calibration eligible: {eligible}")
    if args.compare:
        secondary = load_gold_annotations(args.compare, schema=schema)
        _, metrics = compare_annotators(primary, secondary)
        print(f"raw agreement: {metrics.raw_agreement}")
        print(f"Cohen's kappa: {metrics.cohens_kappa}")
        if not metrics.kappa_defined:
            print(f"kappa undefined: {metrics.kappa_undefined_reason}")


if __name__ == "__main__":
    main()
