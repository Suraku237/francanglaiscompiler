"""Run all repository unittest modules together, including namespace packages."""

import argparse
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEST_DIRECTORIES = tuple(Path(package) / "tests" for package in ("backend", "compiler", "data_collector", "tools"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    modules = []
    for directory in TEST_DIRECTORIES:
        paths = sorted((ROOT / directory).glob("test_*.py"))
        if not paths:
            parser.error(f"No tests found in {directory}.")
        modules.extend(".".join(path.relative_to(ROOT).with_suffix("").parts) for path in paths)
    suite = unittest.defaultTestLoader.loadTestsFromNames(modules)
    result = unittest.TextTestRunner(verbosity=0 if args.quiet else 2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
