"""CLI for verify_chain (FR-05.2)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.audit import verify_chain
from src.config import DB_PATH
from src.database import connect

def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DB_PATH
    if not path.exists():
        print(f"DB not found: {path}")
        return 2
    conn = connect(path)
    res = verify_chain(conn)
    conn.close()
    print(f"VERIFY @ {res.verified_at}")
    print(f"  rows_checked = {res.rows_checked}")
    print(f"  intact       = {res.intact}")
    print(f"  message      = {res.message}")
    return 0 if res.intact else 1

if __name__ == "__main__":
    sys.exit(main())
