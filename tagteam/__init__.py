"""Tag Team Wrestling: your Claude accounts are a tag team, built on claude-swap."""

import os as _os
import sys as _sys

# Windows searches the current directory before PATH; a planted cswap.bat there must never run.
if _sys.platform == "win32":
    _os.environ.setdefault("NoDefaultCurrentDirectoryInExePath", "1")

__version__ = "0.4.4"
