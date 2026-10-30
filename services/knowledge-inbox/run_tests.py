"""Portable CI runner preserving a safe unittest diagnostic artifact on failures."""

import subprocess
import sys
from pathlib import Path

result = subprocess.run(
    [sys.executable, "-m", "unittest", "-v", "test_inbox"],
    capture_output=True,
    text=True,
    encoding="utf-8",
    errors="replace",
)
output = result.stdout + result.stderr
Path("test-output.txt").write_text(output, encoding="utf-8")
print(output)
raise SystemExit(result.returncode)
