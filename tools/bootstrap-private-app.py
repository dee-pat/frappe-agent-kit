#!/usr/bin/env python3
"""Bootstrap a pinned private Frappe app and its guarded GitHub workflow."""

import argparse
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True

from private_app_bootstrap.config import load_config
from private_app_bootstrap.workflow import Bootstrap


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", required=True, type=Path, help="Non-secret JSON configuration"
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Print plan; no network or filesystem changes",
    )
    mode.add_argument(
        "--resume",
        action="store_true",
        help="Resume the same pinned inputs and journal",
    )
    args = parser.parse_args()
    bootstrap = None
    try:
        config = load_config(args.config, Path(__file__).resolve().parent.parent)
        bootstrap = Bootstrap(config, Path(__file__).resolve().parent.parent)
        if args.dry_run:
            bootstrap.plan()
        else:
            bootstrap.run(resume=args.resume)
    except (ValueError, KeyError, OSError, subprocess.SubprocessError) as error:
        message = bootstrap.cmd.redact(str(error)) if bootstrap else str(error)
        print(f"Bootstrap stopped: {message}")
        if bootstrap:
            print(
                f"Resources were preserved. Inspect the journal: {bootstrap.j.path}; retry with --resume."
            )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
