"""Exercise installed GPU processing, AI model inference and the real Qt window."""
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import json
import time
from pathlib import Path
from local_runtime import configure, ROOT

data = configure(ROOT / "local-verification" / "smoke-state")
report_dir = ROOT / "local-verification"
report_dir.mkdir(exist_ok=True)

import onnxruntime as ort
import numpy as np
from PySide6.QtCore import QSettings, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtGui import QFontDatabase, QFont
from core import dust_detect, ccr_processor
from version import VERSION

# Exercise the installed, checksum-verified detector without downloading a
# second copy into the smoke test's isolated settings/catalog directory.
installed_model = ROOT / "local-data" / "appdata" / "FreeCCR" / "models" / "detector.onnx"
assert installed_model.is_file(), "Installed AI dust detector is missing"
dust_detect.model_path = lambda: str(installed_model)

assert ccr_processor._initialize_opencl(), "OpenCL kernel initialization failed"
device = ccr_processor._opencl_cache["device_name"]
assert "RTX 4080" in device, device
rng = np.random.default_rng(42)
image = rng.integers(1000, 60000, (256, 256, 3), dtype=np.uint16)
cpu = ccr_processor.adjust_image(image, contrast=10, saturation=5)
gpu = ccr_processor.adjust_image_opencl(image, contrast=10, saturation=5)
delta = int(np.abs(cpu.astype(np.int32) - gpu.astype(np.int32)).max())
assert delta <= 2, f"CPU/OpenCL difference: {delta}"

if not dust_detect.is_model_present():
    print("Downloading checksum-verified AI dust detector...", flush=True)
    dust_detect.download_model()
session = dust_detect._get_session()
assert session.get_providers()[0] == "DmlExecutionProvider", session.get_providers()
positive = np.full((256, 256, 3), 28000, np.uint16)
positive[120:125, 120:125] = 60000
started = time.perf_counter()
prob, luma = dust_detect.detect(positive)
elapsed = time.perf_counter() - started
assert prob.shape == luma.shape == (256, 256)
assert np.isfinite(prob).all()

app = QApplication([])
QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
app.setFont(QFont("Segoe UI", 9))
from ui.theme import apply_theme
apply_theme(app)
from ui.main_window import MainWindow
window = MainWindow()
window.resize(2400, 1400)
settings_path = Path(window._settings.fileName()).resolve()
assert settings_path.is_relative_to(data), str(settings_path)
window._settings.setValue("installation/version", VERSION)
window._settings.sync()
assert window._settings.status() == QSettings.NoError
# Answer only the smoke test's exit confirmation so headless teardown finishes.
QMessageBox.question = lambda *args, **kwargs: QMessageBox.Yes
window.show()
app.processEvents()
assert window.isVisible()
assert window.grab().save(str(report_dir / "app-preview.png"))
QTimer.singleShot(300, app.quit)
app.exec()
window.close()
app.processEvents()

report = {
    "version": VERSION,
    "python": __import__("sys").version,
    "opencl_device": device,
    "opencl_max_difference_16bit": delta,
    "onnxruntime": ort.__version__,
    "dust_providers": session.get_providers(),
    "dust_dxgi_adapter": os.environ["FREECCR_DML_DEVICE_ID"],
    "dust_model": dust_detect.model_path(),
    "dust_inference_seconds_256px": elapsed,
    "gui_smoke_test": "passed",
    "settings_file": str(settings_path),
}
(report_dir / "setup-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2), flush=True)
