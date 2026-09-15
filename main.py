#!/usr/bin/env python3
"""Entry point for the Franc-anglais compiler. See ``python main.py --help``."""

import sys

from fca.cli import main

if __name__ == "__main__":
    sys.exit(main())
