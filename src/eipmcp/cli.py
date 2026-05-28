"""CLI entry: `eipmcp serve` (MCP stdio) and `eipmcp sync [repo]`."""

from __future__ import annotations

import argparse
import json
import sys

from . import sync as sync_mod
from .config import REPOS, data_dir
from .server import run as run_server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="eipmcp")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("serve", help="Run the MCP server on stdio (default for Claude/IDE).")

    p_sync = sub.add_parser("sync", help="Pull repo(s) and reindex.")
    p_sync.add_argument(
        "repo",
        nargs="?",
        choices=list(REPOS),
        help="Repo to sync. Omit to sync all.",
    )

    sub.add_parser("paths", help="Print the data directory and exit.")

    args = parser.parse_args(argv)

    if args.cmd == "serve":
        run_server()
        return 0

    if args.cmd == "sync":
        if args.repo:
            result = sync_mod.sync_repo(args.repo)
        else:
            result = sync_mod.sync_all()
        json.dump(result, sys.stdout, indent=2, default=str)
        sys.stdout.write("\n")
        return 0

    if args.cmd == "paths":
        print(data_dir())
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
