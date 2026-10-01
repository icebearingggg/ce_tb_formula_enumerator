"""Command-line entry point."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from .config import load_settings
from .enumerator import enumerate_compositions
from .errors import ConfigurationError
from .output import write_outputs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Enumerate reduced Ce/Tb/M/O/F compositions.")
    parser.add_argument("--config", type=Path, required=True, help="UTF-8 JSON configuration path")
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="override output directory; a relative CLI path is resolved from the current directory",
    )
    parser.add_argument("--overwrite", action="store_true", help="replace the four named output files")
    return parser


def run(args: argparse.Namespace) -> dict[str, object]:
    started_at = datetime.now(timezone.utc)
    start_clock = time.perf_counter()
    output_override = args.output_dir.resolve() if args.output_dir is not None else None
    settings = load_settings(args.config, output_override)
    records, stats = enumerate_compositions(settings)
    elapsed_before_write = time.perf_counter() - start_clock
    return write_outputs(
        records,
        settings,
        stats,
        overwrite=args.overwrite,
        started_at=started_at,
        elapsed_seconds=elapsed_before_write,
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        summary = run(args)
    except ConfigurationError as exc:
        parser.exit(2, f"error: {exc}\n")
    except OSError as exc:
        parser.exit(2, f"error: output filesystem operation failed: {exc}\n")
    results = summary["results"]
    print(json.dumps(results, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
