"""Command-line interface.

Three subcommands mirroring the three stages the package covers:

``ingest``     source file -> canonical episodes as JSON Lines
``features``   canonical episodes -> feature table as CSV
``agreement``  two annotator columns -> kappa and an accept/reject verdict
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

from sqmine import __version__
from sqmine.adapters import available_adapters, get_adapter
from sqmine.agreement import DEFAULT_THRESHOLD, score_agreement
from sqmine.features import extract_features, feature_names, summarise
from sqmine.privacy import Pseudonymiser
from sqmine.schema import Episode

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_GATE_FAILED = 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sqmine",
        description="Service-quality episode processing toolkit.",
    )
    parser.add_argument("--version", action="version", version=f"sqmine {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    ingest = sub.add_parser("ingest", help="normalise a source export into episodes")
    ingest.add_argument("input", type=Path, help="source file")
    ingest.add_argument(
        "--adapter", required=True, choices=available_adapters(), help="source adapter"
    )
    ingest.add_argument("--tenant", required=True, help="tenant identifier")
    ingest.add_argument(
        "--key-file", required=True, type=Path, help="pseudonymisation key file"
    )
    ingest.add_argument("--out", type=Path, help="output file (default: stdout)")
    ingest.add_argument(
        "--fail-under",
        type=float,
        default=0.0,
        help="exit non-zero if the acceptance rate falls below this value",
    )

    features = sub.add_parser("features", help="build a feature table from episodes")
    features.add_argument("input", type=Path, help="episodes in JSON Lines")
    features.add_argument("--out", type=Path, help="output CSV (default: stdout)")
    features.add_argument(
        "--stats", action="store_true", help="print descriptive statistics to stderr"
    )

    agreement = sub.add_parser("agreement", help="score inter-annotator agreement")
    agreement.add_argument("input", type=Path, help="CSV of annotator labels")
    agreement.add_argument("--col-a", required=True, help="first annotator column")
    agreement.add_argument("--col-b", required=True, help="second annotator column")
    agreement.add_argument(
        "--threshold", type=float, default=DEFAULT_THRESHOLD, help="minimum kappa"
    )

    return parser


def _cmd_ingest(args: argparse.Namespace, out: TextIO, err: TextIO) -> int:
    pseudonymiser = Pseudonymiser.from_file(args.key_file)
    adapter = get_adapter(args.adapter)(args.tenant, pseudonymiser)
    result = adapter.load(args.input)

    stream = args.out.open("w", encoding="utf-8") if args.out else out
    try:
        for episode in result.episodes:
            stream.write(episode.to_json() + "\n")
    finally:
        if args.out:
            stream.close()

    print(result.summary(), file=err)
    for reject in result.rejects:
        print(f"  row {reject.index}: {reject.reason}", file=err)

    if result.acceptance_rate < args.fail_under:
        print(
            f"acceptance rate {result.acceptance_rate:.1%} is below the "
            f"required {args.fail_under:.1%}",
            file=err,
        )
        return EXIT_GATE_FAILED
    return EXIT_OK


def _cmd_features(args: argparse.Namespace, out: TextIO, err: TextIO) -> int:
    episodes = [
        Episode.from_dict(json.loads(line))
        for line in args.input.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    rows = extract_features(episodes)

    stream = args.out.open("w", newline="", encoding="utf-8") if args.out else out
    try:
        writer = csv.DictWriter(stream, fieldnames=feature_names())
        writer.writeheader()
        for row in rows:
            writer.writerow(row.to_dict())
    finally:
        if args.out:
            stream.close()

    if args.stats:
        for key, value in summarise(rows).items():
            print(f"{key}: {value:.4g}", file=err)
    return EXIT_OK


def _cmd_agreement(args: argparse.Namespace, out: TextIO, err: TextIO) -> int:
    with args.input.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        print("no rows in input", file=err)
        return EXIT_ERROR
    for column in (args.col_a, args.col_b):
        if column not in rows[0]:
            print(f"column {column!r} not found in {args.input}", file=err)
            return EXIT_ERROR

    report = score_agreement(
        [r[args.col_a] for r in rows],
        [r[args.col_b] for r in rows],
        threshold=args.threshold,
    )
    print(report.summary(), file=out)
    return EXIT_OK if report.passed else EXIT_GATE_FAILED


def main(
    argv: Sequence[str] | None = None,
    out: TextIO | None = None,
    err: TextIO | None = None,
) -> int:
    """Entry point. Returns a process exit code instead of calling sys.exit."""
    out = out if out is not None else sys.stdout
    err = err if err is not None else sys.stderr
    args = build_parser().parse_args(argv)

    handlers = {
        "ingest": _cmd_ingest,
        "features": _cmd_features,
        "agreement": _cmd_agreement,
    }
    try:
        return handlers[args.command](args, out, err)
    except (OSError, ValueError, KeyError) as exc:
        print(f"error: {exc}", file=err)
        return EXIT_ERROR


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
