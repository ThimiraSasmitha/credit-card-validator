"""Allow ``python -m ccvalidator``."""

import sys

from .cli import main

sys.exit(main())
