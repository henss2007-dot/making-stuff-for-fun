"""Entry point for the packaged (PyInstaller) BookPress app."""
import sys

from bookpress.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
