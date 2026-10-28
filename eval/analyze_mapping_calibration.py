"""Export validation-only calibration analysis; never selects production policy."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.schema.calibration import analyze_confidence_thresholds, summarize_retrieval_signals


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--output-prefix", type=Path, required=True)
    args = parser.parse_args()
    observations = pd.read_csv(args.observations)
    args.output_prefix.parent.mkdir(parents=True, exist_ok=True)
    summarize_retrieval_signals(observations).to_csv(
        args.output_prefix.with_name(args.output_prefix.name + "_signals.csv"), index=False
    )
    analyze_confidence_thresholds(observations).to_csv(
        args.output_prefix.with_name(args.output_prefix.name + "_risk_coverage.csv"), index=False
    )


if __name__ == "__main__":
    main()
