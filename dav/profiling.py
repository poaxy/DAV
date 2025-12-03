"""Profiling helpers for the Dav CLI.

This module is intentionally lightweight and only used when you
explicitly invoke it (e.g. ``python -m dav.profiling -- ...``).
It has no impact on normal ``dav`` CLI performance.
"""

from __future__ import annotations

import cProfile
import pstats
import sys
from io import StringIO
from typing import List, Optional

from .cli import app


def profile_main(argv: Optional[List[str]] = None, sort_by: str = "tottime") -> None:
    """Run the Typer app under cProfile and print a concise report.

    Usage (from repo or installed environment):

        python -m dav.profiling -- how do I check disk usage?

    Everything after ``--`` is treated as normal ``dav`` arguments.
    """
    # Determine arguments to pass through to Typer
    if argv is None:
        # When invoked as ``python -m dav.profiling -- ...``,
        # everything after ``--`` is for Dav.
        if "--" in sys.argv:
            idx = sys.argv.index("--")
            dav_args = sys.argv[idx + 1 :]
        else:
            dav_args = sys.argv[1:]
    else:
        dav_args = list(argv)

    profiler = cProfile.Profile()

    # Preserve original argv so we don't affect callers
    original_argv = sys.argv
    try:
        sys.argv = [original_argv[0]] + dav_args
        profiler.enable()
        try:
            # Typer app will typically raise SystemExit after completion
            app()
        except SystemExit:
            # Normal Typer exit; we still want the profile
            pass
        finally:
            profiler.disable()
    finally:
        sys.argv = original_argv

    # Format profiling output
    buffer = StringIO()
    stats = pstats.Stats(profiler, stream=buffer).strip_dirs().sort_stats(sort_by)
    # Print a reasonably small number of lines to keep output useful
    stats.print_stats(40)

    print("\n=== Dav profiling summary (sorted by {}) ===".format(sort_by))
    print(buffer.getvalue())


if __name__ == "__main__":
    profile_main()


