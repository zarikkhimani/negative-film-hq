"""Keep this source installation's settings, models and caches in the workspace."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def configure(data=None):
    data = Path(data) if data is not None else ROOT / "local-data"
    for name in ("appdata", "cache", "tmp", "settings", "logs"):
        (data / name).mkdir(parents=True, exist_ok=True)
    os.environ["APPDATA"] = str(data / "appdata")
    os.environ["LOCALAPPDATA"] = str(data / "cache")
    os.environ["TEMP"] = os.environ["TMP"] = str(data / "tmp")
    os.environ["PYOPENCL_CACHE_DIR"] = str(data / "cache" / "opencl")
    os.environ["XDG_CACHE_HOME"] = str(data / "cache")
    os.environ["FREECCR_EXPORT_DIRECTORY"] = str(ROOT.parent / "NegativeLab" / "Results")
    # Windows known-folder APIs ignore process-local LOCALAPPDATA overrides.
    # Redirect platformdirs' cache resolver in this process before PyOpenCL's
    # persistent kernel-invoker cache is imported.
    import platformdirs
    def workspace_cache_dir(appname=None, appauthor=None, version=None,
                            opinion=True, ensure_exists=False):
        path = data / "cache" / (appname or "default")
        if version:
            path /= version
        if ensure_exists:
            path.mkdir(parents=True, exist_ok=True)
        return str(path)
    platformdirs.user_cache_dir = workspace_cache_dir
    sys.path.insert(0, str(ROOT / "src"))
    # ONNX Runtime must load before Qt on Windows, as required by FreeCCR.
    import onnxruntime
    from local_gpu_probe import dxgi_adapters
    matches = [a for a in dxgi_adapters() if "RTX 4080" in a["name"]]
    if len(matches) != 1:
        raise RuntimeError("Expected exactly one RTX 4080 DXGI adapter")
    gpu = matches[0]
    os.environ["FREECCR_DML_DEVICE_ID"] = str(gpu["index"])
    import pyopencl as cl
    devices = [d for p in cl.get_platforms() for d in p.get_devices()
               if "RTX 4080" in d.name]
    if len(devices) != 1:
        raise RuntimeError("Expected exactly one RTX 4080 OpenCL device")
    os.environ["FREECCR_OPENCL_DEVICE"] = devices[0].name.strip()
    print(f"GPU: {gpu['name']} (DirectML adapter {gpu['index']})", flush=True)
    from PySide6.QtCore import QSettings
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(data / "settings"))
    QSettings.setPath(QSettings.IniFormat, QSettings.SystemScope, str(data / "settings"))
    return data
