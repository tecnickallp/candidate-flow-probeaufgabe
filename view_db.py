"""Browse the local SQLite database (data/app.db) in a web UI."""
from __future__ import annotations

import subprocess
import sys

import config

PORT = 8080
HOST = "127.0.0.1"


def main() -> None:
    db_path = config.DATA_DIR / "app.db"
    if not db_path.exists():
        print(f"Keine Datenbank gefunden: {db_path}")
        sys.exit(1)

    print(f"SQLite Web UI: http://{HOST}:{PORT}/")
    print(f"Datenbank: {db_path}")
    print("Beenden mit Strg+C")

    subprocess.run(
        [
            sys.executable,
            "-m",
            "sqlite_web",
            str(db_path),
            "--host",
            HOST,
            "--port",
            str(PORT),
            "-r",
            "-x",
        ],
        check=True,
    )


if __name__ == "__main__":
    main()
