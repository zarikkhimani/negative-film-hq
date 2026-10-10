"""Exercise real drag/drop, the three converter choices, cancellation and editor arguments."""
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["PYTHONIOENCODING"] = "utf-8"

import json
from pathlib import Path
import time

from app import QApplication, MainWindow, configure_application

import numpy as np
import tifffile
from PySide6.QtCore import Qt, QMimeData, QUrl, QPointF
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMessageBox

from engine import HERE, WORKSPACE, read_preview, sha256, new_job_path

OUT = HERE / "test-output"
OUT.mkdir(exist_ok=True)
import app as ui
ui.new_job_path = lambda: new_job_path(OUT / "gui-jobs")
ui.RESULTS = OUT / "converted"
sample, info = read_preview(WORKSPACE / "Samples" / "Signynt" / "Example.tif", 1000)
source = OUT / "GUI negative sample.tif"
tifffile.imwrite(source, sample, photometric="rgb", compression="deflate", resolution=(4800, 4800), resolutionunit="INCH")
source_hash = sha256(source)

application = QApplication([])
configure_application(application)
warnings = []
QMessageBox.warning = lambda *args: warnings.append(str(args[-1]))
window = MainWindow()
window.show()
application.processEvents()


def wait_ready(seconds=90):
    deadline = time.monotonic() + seconds
    while window.busy and time.monotonic() < deadline:
        application.processEvents()
        QTest.qWait(20)
    assert not window.busy, "Job exceeded test deadline"
    application.processEvents()


mime = QMimeData()
mime.setUrls([QUrl.fromLocalFile(str(source))])
view = window.views["negative"]
enter = QDragEnterEvent(view.contentsRect().center(), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
application.sendEvent(view, enter)
assert enter.isAccepted()
drop = QDropEvent(QPointF(view.contentsRect().center()), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
application.sendEvent(view, drop)
wait_ready()
assert window.source == source.resolve()
assert window.convert_button.isEnabled()
assert window.grab().save(str(OUT / "negative-workspace.jpg"), "JPG", 94)

reports = {}
for mode in ("freeccr", "negadoctor", "both"):
    window.mode.setCurrentIndex(window.mode.findData(mode))
    QTest.mouseClick(window.convert_button, Qt.LeftButton)
    wait_ready()
    assert window.report and window.report["status"] == "complete", window.report
    expected = {"freeccr", "negadoctor"} if mode == "both" else {mode}
    assert set(window.results) == expected
    assert window.finish_button.isEnabled()
    for result in window.results.values():
        assert Path(result["path"]).parent == ui.RESULTS
        assert Path(result["preview"]).parent == ui.RESULTS
        output = tifffile.imread(result["path"])
        assert output.shape == sample.shape and output.dtype == np.uint16
    assert window.report["original_preserved"]
    reports[mode] = str(window.job / "job.json")
    if mode == "both":
        assert window.tabs.currentIndex() == 3
        assert window.grab().save(str(OUT / "comparison-workspace.jpg"), "JPG", 94)

# The folder action always opens the shared output directory, including before a new job.
assert all(path.is_file() for path in ui.RESULTS.iterdir())
opened = []
real_open_url = ui.QDesktopServices.openUrl
try:
    ui.QDesktopServices.openUrl = lambda url: opened.append(url.toLocalFile())
    window.open_results()
finally:
    ui.QDesktopServices.openUrl = real_open_url
assert [Path(path) for path in opened] == [ui.RESULTS]

# Sample a patch through the actual viewer coordinates and exercise the advanced panel.
window.advanced.setChecked(True)
window.sample_base()
application.processEvents()
view = window.views["negative"]
QTest.mouseClick(view, Qt.LeftButton, pos=view.image_rect.center().toPoint())
assert window.base_rgb is not None
window.clear_base()
assert window.base_rgb is None
window.resize(1000, 720)
application.processEvents()
assert window.grab().save(str(OUT / "settings-workspace.jpg"), "JPG", 94)

# Cancel immediately, including the race before the worker creates its job directory.
window.mode.setCurrentIndex(window.mode.findData("both"))
QTest.mouseClick(window.convert_button, Qt.LeftButton)
window.cancel()
wait_ready()
assert window.report["status"] == "cancelled", window.report
assert not list(window.job.glob("*.partial.tif"))

# Cancel after darktable has been started, not only before the worker launches.
window.start_job("negadoctor")
deadline = time.monotonic() + 30
while not (window.job / "negadoctor.log").exists() and time.monotonic() < deadline:
    application.processEvents()
    QTest.qWait(20)
assert (window.job / "negadoctor.log").exists()
QTest.qWait(300)
window.cancel()
wait_ready()
assert window.report["status"] == "cancelled", window.report
assert not (window.job / "negadoctor.tif").exists()
assert not list(window.job.glob("*.partial.tif"))

# Prepare editable Negadoctor copy without opening windows during this headless check.
window.start_job("prepare")
wait_ready()
assert window.report["status"] == "complete"
assert Path(window.report["negative"] + ".xmp").is_file()

# Inspect launching both real editors through their exact commands; avoid disrupting open apps.
commands = []
real_popen = ui.subprocess.Popen
try:
    ui.subprocess.Popen = lambda command, **kwargs: commands.append((command, kwargs))
    window.open_editor("freeccr")
    window.open_editor("negadoctor")
finally:
    ui.subprocess.Popen = real_popen
assert len(commands) == 2
assert commands[0][0][-1] == window.report["negative"]
assert "--library" in commands[1][0]
assert Path(commands[1][0][-1]) == Path(window.report["negative"])
assert commands[1][1]["env"]["APPDATA"].startswith(str(window.job))
assert source_hash == sha256(source)

report = dict(gui_drag_drop=True, modes=reports, immediate_cancel=True, film_base_picker=True,
              shared_results_folder=True,
              darktable_cancel=True,
              prepare_editor_sidecar=True, editor_command_checks=True, actual_editor_windows_tested=False,
              original_preserved=True)
(OUT / "gui-smoke.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
assert not warnings, warnings
window.close()
application.processEvents()
