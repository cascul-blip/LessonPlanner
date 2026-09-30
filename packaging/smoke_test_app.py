"""Start a built LessonPlanner executable headless and check it stays up.

Usage: python packaging/smoke_test_app.py path/to/LessonPlanner[.exe]
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

RUN_SECONDS = 15


def main() -> None:
    with tempfile.TemporaryDirectory() as folder:
        env = {**os.environ, "LESSONPLANNER_DB_FOLDER": folder, "QT_QPA_PLATFORM": "offscreen"}
        proc = subprocess.Popen([os.path.abspath(sys.argv[1])], env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        try:
            out, _ = proc.communicate(timeout=RUN_SECONDS)
            sys.exit(f"App exited early with code {proc.returncode}:\n{out.decode(errors='replace')}")
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
        created = sorted(p.name for p in Path(folder).iterdir())
        if "lessonplanner.db" not in created:
            sys.exit(f"App did not create its database; folder has {created}")
        print(f"OK: app ran {RUN_SECONDS}s and created {created}")


if __name__ == "__main__":
    main()
