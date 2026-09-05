"""PyInstaller entry point. Absolute import so the package's relative imports resolve."""

import sys

from cfb_ticker.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
