#!/usr/bin/env python3
"""Fit/freeze development responses or summarize evaluation using that frozen model."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from finbot.clarification_study import fit_model, summarize


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["fit", "evaluate"])
    parser.add_argument("inputs", type=Path, nargs="+", help="Downloaded session exports")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", type=Path, help="Required frozen model for evaluation")
    parser.add_argument("--allow-rehearsal", action="store_true", help="Infrastructure check; never human evidence")
    args = parser.parse_args()
    try:
        exports = [json.loads(p.read_text()) for p in args.inputs]
        if args.action == "fit":
            if args.model:
                parser.error("Do not supply --model when fitting.")
            result = fit_model(exports, allow_rehearsal=args.allow_rehearsal)
        else:
            if not args.model:
                parser.error("Evaluation requires --model from the development phase.")
            result = summarize(exports, json.loads(args.model.read_text()), allow_rehearsal=args.allow_rehearsal)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        # A freeze cannot silently overwrite an earlier model or report.
        with args.output.open("x") as handle:
            json.dump(result, handle, indent=2, allow_nan=False)
            handle.write("\n")
    except (OSError, ValueError, TypeError, KeyError) as exc:
        parser.exit(2, f"Study analysis refused: {exc}\n")
    print(f"Saved {result['provenance']} artifact to {args.output}")


if __name__ == "__main__":
    main()
