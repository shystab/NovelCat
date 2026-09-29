"""Reset a NovelCat account password using the app's own hash format.

Usage:
    python scripts/reset_password.py --username shysta --password "new-password"
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
DB_PATH = BACKEND_DIR / "novel_ide.db"


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset a NovelCat account password")
    parser.add_argument("--username", required=True, help="Username to reset")
    parser.add_argument("--password", required=True, help="New password (at least 8 characters)")
    args = parser.parse_args()

    username = args.username.strip()
    password = args.password
    if len(password) < 8:
        print("Password must be at least 8 characters.", file=sys.stderr)
        return 1
    if not DB_PATH.exists():
        print(f"Database not found: {DB_PATH}", file=sys.stderr)
        return 1

    sys.path.insert(0, str(BACKEND_DIR))
    from app.core.auth import hash_password

    password_hash = hash_password(password)
    con = sqlite3.connect(DB_PATH)
    try:
        cursor = con.execute("UPDATE user SET password_hash = ? WHERE username = ?", (password_hash, username))
        con.commit()
    finally:
        con.close()

    if cursor.rowcount == 0:
        print(f"No user named '{username}' found. Nothing changed.")
        return 1

    print(f"Password reset for '{username}'. You can log in with the new password now.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
