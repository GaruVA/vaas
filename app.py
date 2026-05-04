"""
╔══════════════════════════════════════════════════════════════╗
║  WRONG FILE — do not run this directly.                      ║
║                                                              ║
║  To start VAAS:                                              ║
║      python serve.py                                         ║
║                                                              ║
║  serve.py uses the Waitress WSGI server, loads your .env     ║
║  file automatically, validates your configuration, and       ║
║  starts the live camera worker threads.                      ║
╚══════════════════════════════════════════════════════════════╝
"""
import sys
import textwrap

_MSG = textwrap.dedent("""

    ╔══════════════════════════════════════════════════════════════╗
    ║  ERROR: You ran  python app.py                               ║
    ║                                                              ║
    ║  This file is not the application entry point.              ║
    ║  Please run:  python serve.py                               ║
    ╚══════════════════════════════════════════════════════════════╝
""")

if __name__ == "__main__":
    print(_MSG, file=sys.stderr)
    sys.exit(1)

# ── Kept only so `flask --app app` still works during unit-testing ──────────
# Production code must use serve.py.
from webapp import create_app          # noqa: E402
app = create_app()
