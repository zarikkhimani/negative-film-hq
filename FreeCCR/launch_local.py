"""Launch FreeCCR with workspace-local state and a persistent diagnostic log."""
import ctypes
import os
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent
log_dir = ROOT / "local-data" / "logs"
log_dir.mkdir(parents=True, exist_ok=True)
log_path = log_dir / "launch.log"
with log_path.open("w", encoding="utf-8", buffering=1) as log:
    sys.stdout = sys.stderr = log
    try:
        from local_runtime import configure
        configure()
        os.chdir(ROOT)
        sys.argv[0] = str(ROOT / "src" / "main.py")
        from core.ccr_processor import _initialize_opencl
        if not _initialize_opencl():
            raise RuntimeError("The configured RTX 4080 OpenCL kernel could not initialize")
        # Since v2.2.0 upstream handles file/folder arguments and its TIFF
        # colour-space import dialog. Keep the local GPU/state configuration
        # while using that supported startup path.
        from main import main
        main()
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        log.flush()
        ctypes.windll.user32.MessageBoxW(
            None, f"FreeCCR could not start. Details are in:\n{log_path}",
            "FreeCCR startup error", 0x10)
        raise
