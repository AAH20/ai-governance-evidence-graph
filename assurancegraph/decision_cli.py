"""Offline-first shadow decision pilot CLI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .decisions import FixtureProvider, JevProvider, assurance_envelope, run_pack


def main() -> int:
    parser = argparse.ArgumentParser(prog="assurancegraph-decisions")
    parser.add_argument("pack", type=Path)
    parser.add_argument("--provider", choices=("fixture", "jev"), default="fixture")
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--assurance-output", type=Path)
    args = parser.parse_args()
    try:
        pack = json.loads(args.pack.read_text(encoding="utf-8"))
        provider = (
            FixtureProvider()
            if args.provider == "fixture"
            else JevProvider(allow_network=args.allow_network)
        )
        report = run_pack(pack, provider)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    if args.assurance_output:
        args.assurance_output.parent.mkdir(parents=True, exist_ok=True)
        args.assurance_output.write_text(
            json.dumps(
                assurance_envelope(pack, report),
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
            + "\n",
            encoding="utf-8",
        )
    print(
        json.dumps(
            {
                "cases": report["summary"]["cases"],
                "correct": report["summary"]["correct"],
                "provider": report["provider"],
                "shadow_only": True,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
