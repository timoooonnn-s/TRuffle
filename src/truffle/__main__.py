"""`python3 -m truffle` (with src/ on the path) - the same as the `truffle` launcher."""

import sys

from .cli import main

sys.exit(main())
