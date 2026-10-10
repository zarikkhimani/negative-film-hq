"""Exercise manual SwinIR actions with the installed checkpoint on the actual GPU."""
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import json
from pathlib import Path
import time

from app import QApplication, MainWindow, configure_application
import app as ui
import numpy as np
from PIL import Image
import tifffile
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMessageBox

from engine import HERE, WORKSPACE, new_job_path, read_preview, sha256, inspect_image

OUT = HERE / "test-output" / "swinir-gui"
OUT.mkdir(parents=True, exist_ok=True)
ui.new_job_path = lambda: new_job_path(OUT / "jobs")
ui.RESULTS = OUT / "converted"
sample, _ = read_preview(WORKSPACE / "Samples" / "Signynt" / "Example.tif", 240)
negative = np.ascontiguousarray(sample[40:136, 20:148])
source = OUT / "negative.tif"
tifffile.imwrite(source, negative, photometric="rgb", compression="deflate", resolution=(4800, 4800), resolutionunit="INCH")
original_hash = sha256(source)
application = QApplication([])
configure_application(application)
warnings = []
QMessageBox.warning = lambda *args: warnings.append(str(args[-1]))
window = MainWindow()
window.show()


def wait_ready(seconds=120):
    deadline = time.monotonic() + seconds
    while window.busy and time.monotonic() < deadline:
        application.processEvents()
        QTest.qWait(20)
    assert not window.busy, "SwinIR smoke test exceeded deadline"
    application.processEvents()


def assert_upscale(input_path):
    assert window.report["status"] == "complete", window.report
    result = window.results["swinir"]
    assert Path(result["path"]).parent == ui.RESULTS
    assert Path(result["preview"]).parent == ui.RESULTS
    before = inspect_image(input_path)
    after = inspect_image(result["path"])
    assert (after["width"], after["height"]) == (before["width"] * 2, before["height"] * 2)
    assert after["bits"] == 16 and after["dpi"] == before["dpi"]
    if Path(input_path).suffix.lower() in (".tif", ".tiff"):
        with tifffile.TiffFile(input_path) as tf:
            source_icc = tf.pages[0].tags[34675].value
    else:
        with Image.open(input_path) as image:
            source_icc = image.info["icc_profile"]
    with tifffile.TiffFile(result["path"]) as tf:
        assert tf.pages[0].tags[34675].value == source_icc
    assert window.tabs.currentIndex() == 4
    assert window.report["original_preserved"]
    assert result["settings"]["device"] == "cuda"
    return str(window.job / "job.json")


window.load_file(str(source))
wait_ready()
assert not window.results and window.process is None
window.mode.setCurrentIndex(window.mode.findData("both"))
QTest.mouseClick(window.convert_button, Qt.LeftButton)
wait_ready()
assert set(window.results) == {"freeccr", "negadoctor"}, "SwinIR must not run during normal conversion"
negative_report = window.negative_report
base_results = {key: result["path"] for key, result in window.results.items()}
base_hashes = {key: sha256(path) for key, path in base_results.items()}
with tifffile.TiffFile(base_results["freeccr"]) as tf:
    icc = tf.pages[0].tags[34675].value

reports = {}
for key in ("freeccr", "negadoctor"):
    window.tabs.setCurrentIndex(3)
    window.result_choice.setCurrentIndex(window.result_choice.findData(key))
    assert window.upscale_button.isEnabled()
    QTest.mouseClick(window.upscale_button, Qt.LeftButton)
    wait_ready()
    assert window.negative_report is negative_report
    assert {"freeccr", "negadoctor", "swinir"} == set(window.results)
    reports[key] = assert_upscale(base_results[key])
    assert base_hashes[key] == sha256(base_results[key])
assert sha256(source) == original_hash
assert window.grab().save(str(OUT / "swinir-workspace.jpg"), "JPG", 94)

# A separately loaded positive remains idle until the user clicks the action.
positive = OUT / "existing-positive.jpg"
pixels = tifffile.imread(base_results["freeccr"])
Image.fromarray((pixels // 257).astype(np.uint8)).save(positive, quality=95, icc_profile=icc, dpi=(4800, 4800))
positive_hash = sha256(positive)
window.source_kind.setCurrentIndex(window.source_kind.findData("positive"))
window.load_file(str(positive))
wait_ready()
assert not window.results and window.process is None
assert not window.free_editor.isEnabled() and not window.dark_editor.isEnabled()
QTest.mouseClick(window.convert_button, Qt.LeftButton)
wait_ready()
reports["existing_positive"] = assert_upscale(positive)
assert sha256(positive) == positive_hash

# Cancel the actual SwinIR process after inference is announced in its log.
large_positive = OUT / "cancellation-positive.tif"
tifffile.imwrite(large_positive, np.tile(pixels, (4, 4, 1)), photometric="rgb", iccprofile=icc)
window.load_file(str(large_positive))
wait_ready()
QTest.mouseClick(window.convert_button, Qt.LeftButton)
deadline = time.monotonic() + 45
log = window.job / "swinir.log"
while window.busy and time.monotonic() < deadline:
    application.processEvents()
    if log.exists() and "[1/1]" in log.read_text(encoding="utf-8", errors="replace"):
        break
    QTest.qWait(20)
assert window.busy and log.exists()
window.cancel()
wait_ready()
assert window.report["status"] == "cancelled", window.report
assert not (window.job / "swinir-x2.tif").exists()
assert not list(window.job.glob("*.partial.tif"))
assert not list((window.job / "swinir-work").glob("*.tif"))

report = dict(manual_only=True, gpu_inference=True, profiles_and_dpi_preserved=True,
              converted_masters_preserved=True, existing_positive=True, cancellation=True, jobs=reports)
(OUT / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
assert not warnings, warnings
window.close()
application.processEvents()
