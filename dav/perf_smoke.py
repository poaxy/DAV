"""Simple performance smoke tests for Dav.

This module is optional and not used by the normal ``dav`` CLI. It exists
so you can quickly measure wall‑clock times for a few common scenarios.

Example usage (from the project root or an installed environment):

    python -m dav.perf_smoke single \"how do I check disk usage?\"

The tests are intentionally lightweight and do not assert on results – they
only report timings so you can compare before/after optimisations.
"""

from __future__ import annotations

import sys
import time
from typing import List

from .cli import app


def _run_once(args: List[str]) -> float:
    """Run the Typer app once with the given arguments and return duration."""
    # Temporarily override sys.argv so the Typer app sees the desired args.
    original_argv = sys.argv
    sys.argv = [original_argv[0]] + args

    start = time.perf_counter()
    try:
        try:
            app()
        except SystemExit:
            # Normal Typer exit; ignore for timing.
            pass
    finally:
        end = time.perf_counter()
        sys.argv = original_argv

    return end - start


def run_single_query(query: str, repeats: int = 3) -> None:
    """Run a single non‑interactive query multiple times and print stats."""
    print(f"Running single‑query smoke test ({repeats} run(s))...")
    durations: List[float] = []
    for i in range(repeats):
        dt = _run_once([query])
        durations.append(dt)
        print(f"  Run {i + 1}: {dt:.3f}s")
    if durations:
        sorted_dt = sorted(durations)
        median = sorted_dt[len(sorted_dt) // 2]
        p95 = sorted_dt[int(len(sorted_dt) * 0.95) - 1]
        print(f"Median: {median:.3f}s, 95th percentile (approx): {p95:.3f}s")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Dav performance smoke tests")
    subparsers = parser.add_subparsers(dest="command", required=True)

    single = subparsers.add_parser("single", help="Run a single non‑interactive query")
    single.add_argument("query", help="Query string to send to Dav")
    single.add_argument(
        "--repeats",
        type=int,
        default=3,
        help="Number of times to repeat the query (default: 3)",
    )

    args = parser.parse_args()

    if args.command == "single":
        run_single_query(args.query, repeats=args.repeats)


if __name__ == "__main__":
    main()


