"""Run the relevant upstream tests in isolated processes with local-only state."""
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parent
out = root / "local-verification"
out.mkdir(exist_ok=True)
test_files = sys.argv[1:] or ["test_scanner_tiff.py", "test_export.py", "test_density_bwpoint.py",
              "test_dust_removal.py", "test_opencl_accuracy.py", "test_settings_dialog.py"]
results = []
for name in test_files:
    code = (
        "import os; os.environ['QT_QPA_PLATFORM']='offscreen'; "
        "from local_runtime import configure, ROOT; "
        "configure(ROOT/'local-verification'/'test-state'); "
        "import pytest, sys; sys.exit(pytest.main(sys.argv[1:]))"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code, str(root / "tests" / name), "-q",
         "-p", "no:cacheprovider", "--basetemp", str(out / ("tmp-" + name))],
        cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace")
    log = proc.stdout + proc.stderr
    (out / (name + ".log")).write_text(log, encoding="utf-8")
    print(f"{name}: exit {proc.returncode}\n{log[-1800:]}", flush=True)
    results.append(proc.returncode)
sys.exit(0 if all(code == 0 for code in results) else 1)
