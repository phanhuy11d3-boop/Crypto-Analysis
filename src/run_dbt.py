"""Run dbt against this project's PostgreSQL using its local .env and profile."""
import os
import json
import shutil
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent


def main():
    load_dotenv(ROOT / ".env")
    executable = Path(sys.executable).with_name("dbt.exe" if os.name == "nt" else "dbt")
    command = str(executable) if executable.exists() else shutil.which("dbt")
    if not command:
        raise RuntimeError("Install the project's requirements to run dbt")
    env = dict(os.environ, DBT_SEND_ANONYMOUS_USAGE_STATS="false")
    args = sys.argv[1:] or ["build"]
    if args[0] in ("build", "run", "test"):
        status_path = ROOT / "data/raw/linea_transactions.status.json"
        if not status_path.exists() or not json.loads(status_path.read_text(encoding="utf-8")).get("complete"):
            print("NOTE: API completeness is unverified/incomplete. dbt uses existing database rows; successful tests do not prove complete extraction.", flush=True)
    return subprocess.call([command, *args, "--project-dir", str(ROOT / "dbt"),
                            "--profiles-dir", str(ROOT / "dbt")], cwd=ROOT, env=env)


if __name__ == "__main__":
    sys.exit(main())
