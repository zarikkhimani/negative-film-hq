"""NegativeLab's native drag-and-drop workspace. Start with the parent .cmd launcher."""
from __future__ import annotations

import codecs
import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
import traceback

# FreeCCR requires ONNX Runtime to load before Qt on Windows.
import onnxruntime  # noqa: F401
import numpy as np
from PySide6.QtCore import Qt, Signal, QThread, QProcess, QProcessEnvironment, QUrl, QRectF, QSize
from PySide6.QtGui import QImage, QPixmap, QPainter, QColor, QFont, QFontDatabase, QDesktopServices
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                              QLabel, QPushButton, QFileDialog, QComboBox, QDoubleSpinBox,
                              QFormLayout, QTabWidget, QSplitter, QProgressBar, QMessageBox,
                              QCheckBox, QScrollArea)

from engine import (HERE, WORKSPACE, FREECCR, DARKTABLE, RESULTS, SUPPORTED, read_preview, new_job_path,
                    darktable_environment)

STYLE = """
QWidget { background: #181a1c; color: #eeeae3; font-family: 'Segoe UI'; font-size: 13px; }
QLabel#brand { font-size: 27px; font-weight: 650; letter-spacing: -1px; }
QLabel#quiet { color: #979b9e; }
QLabel#section { color: #c2c2bc; font-size: 11px; font-weight: 650; letter-spacing: 1px; }
QWidget#inspector { background: #202325; border-right: 1px solid #343739; }
QWidget#inspector QLabel, QWidget#inspector QCheckBox { background: transparent; }
QPushButton { border: 1px solid #464b4d; border-radius: 5px; padding: 10px 12px; background: #292d30; }
QPushButton:hover { background: #343a3e; border-color: #7c807d; }
QPushButton:pressed { background: #43494d; }
QPushButton:disabled { color: #73777a; border-color: #34383b; background: #242729; }
QPushButton#primary { background: #e4ad67; color: #201b15; border: 0; font-weight: 650; padding: 13px; }
QPushButton#primary:hover { background: #f0be81; }
QPushButton#primary:disabled { background: #65543e; color: #aaa092; }
QComboBox, QDoubleSpinBox { padding: 8px; background: #171a1c; border: 1px solid #45494c; border-radius: 4px; }
QComboBox QAbstractItemView { selection-background-color: #65543e; }
QTabWidget::pane { border: 0; }
QTabBar::tab { padding: 13px 22px; color: #a3a7a9; border-bottom: 2px solid transparent; background: #202325; }
QTabBar::tab:selected { color: #f0c185; border-bottom: 2px solid #e4ad67; }
QTabBar::tab:disabled { color: #616669; }
QProgressBar { border: 0; background: #292d30; height: 3px; }
QProgressBar::chunk { background: #e4ad67; }
QSplitter::handle { background: #343739; width: 2px; }
QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 16px; height: 16px; }
QToolTip { color: #eeeae3; background: #343739; border: 1px solid #5c6061; }
"""


def label(text, name=None, wrap=False):
    item = QLabel(text)
    if name:
        item.setObjectName(name)
    item.setWordWrap(wrap)
    return item


def button(text, callback, primary=False):
    item = QPushButton(text)
    item.setCursor(Qt.PointingHandCursor)
    if primary:
        item.setObjectName("primary")
    item.clicked.connect(callback)
    return item


def configure_application(app):
    app.setApplicationName("NegativeLab")
    app.setStyle("Fusion")
    # Register the installed Windows font explicitly so offscreen validation also renders text.
    font_dir = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    for name in ("segoeui.ttf", "seguisb.ttf"):
        font = font_dir / name
        if font.is_file():
            QFontDatabase.addApplicationFont(str(font))
    app.setFont(QFont("Segoe UI", 9))
    app.setStyleSheet(STYLE)


class PreviewLoader(QThread):
    loaded = Signal(object, object)
    failed = Signal(str)

    def __init__(self, path):
        super().__init__()
        self.path = path

    def run(self):
        try:
            pixels, info = read_preview(self.path)
            self.loaded.emit(pixels, info)
        except Exception as exc:
            self.failed.emit(str(exc))


class ImageView(QWidget):
    dropped = Signal(str)
    sample = Signal(float, float)
    browse = Signal()

    def __init__(self, empty="Drop a negative here\nTIFF or JPEG · or click to browse"):
        super().__init__()
        self.empty = empty
        self.pixmap = None
        self.dragging = False
        self.sampling = False
        self.last_sample = None
        self.image_rect = QRectF()
        self.setAcceptDrops(True)
        self.setMinimumSize(180, 200)

    def set_pixels(self, pixels):
        display = np.ascontiguousarray((pixels // 257).astype(np.uint8))
        image = QImage(display.data, display.shape[1], display.shape[0], display.strides[0], QImage.Format_RGB888).copy()
        self.pixmap = QPixmap.fromImage(image)
        self.last_sample = None
        self.update()

    def set_preview(self, path):
        self.pixmap = QPixmap(str(path))
        if self.pixmap.isNull():
            raise ValueError(f"Cannot read result preview: {path}")
        self.update()

    def clear(self):
        self.pixmap = None
        self.last_sample = None
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.contentsRect(), QColor("#131517"))
        if self.pixmap is None:
            painter.setPen(QColor("#e9b77a" if self.dragging else "#c9c8c2"))
            painter.setFont(QFont("Segoe UI", 19))
            painter.drawText(self.contentsRect().adjusted(32, 32, -32, -32), Qt.AlignCenter, self.empty)
        else:
            size = self.pixmap.size().scaled(self.size() - QSize(48, 48), Qt.KeepAspectRatio)
            self.image_rect = QRectF((self.width() - size.width()) / 2, (self.height() - size.height()) / 2,
                               size.width(), size.height())
            painter.setRenderHint(QPainter.SmoothPixmapTransform)
            painter.drawPixmap(self.image_rect, self.pixmap, QRectF(self.pixmap.rect()))
            if self.last_sample:
                x, y = self.last_sample
                painter.setPen(QColor("#f0bc78"))
                painter.drawEllipse(QRectF(self.image_rect.x() + x * self.image_rect.width() - 7,
                                          self.image_rect.y() + y * self.image_rect.height() - 7, 14, 14))
        if self.dragging:
            painter.setPen(QColor("#e4ad67"))
            painter.drawRect(self.contentsRect().adjusted(8, 8, -9, -9))

    def dragEnterEvent(self, event):
        urls = event.mimeData().urls()
        if len(urls) == 1 and urls[0].isLocalFile() and Path(urls[0].toLocalFile()).suffix.lower() in SUPPORTED:
            event.acceptProposedAction()
            self.dragging = True
            self.update()

    def dragLeaveEvent(self, event):
        self.dragging = False
        self.update()

    def dropEvent(self, event):
        self.dragging = False
        self.update()
        self.dropped.emit(event.mimeData().urls()[0].toLocalFile())
        event.acceptProposedAction()

    def mousePressEvent(self, event):
        if self.pixmap is None:
            self.browse.emit()
        elif self.sampling and self.image_rect.contains(event.position()):
            x = (event.position().x() - self.image_rect.x()) / self.image_rect.width()
            y = (event.position().y() - self.image_rect.y()) / self.image_rect.height()
            self.last_sample = (x, y)
            self.sample.emit(x, y)
            self.update()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.source = None
        self.pixels = None
        self.info = None
        self.results = {}
        self.job = None
        self.process = None
        self.loader = None
        self.busy = False
        self.pending_editor = None
        self.closing = False
        self.buffer = ""
        self.base_rgb = None
        self.report = None
        self.negative_report = None
        self.current_mode = None
        self.last_error = None
        self.setWindowTitle("NegativeLab — FreeCCR + darktable + SwinIR")
        self.resize(1320, 850)
        self.setMinimumSize(1000, 720)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        header = QHBoxLayout()
        header.setContentsMargins(25, 18, 25, 18)
        header.addWidget(label("NegativeLab", "brand"))
        header.addWidget(label("  CONVERT + UPSCALE", "quiet"))
        header.addStretch()
        header.addWidget(label("FreeCCR · darktable / Negadoctor · SwinIR", "quiet"))
        layout.addLayout(header)
        body = QHBoxLayout()
        body.setSpacing(0)
        inspector = QWidget()
        inspector.setObjectName("inspector")
        side = QVBoxLayout(inspector)
        side.setContentsMargins(22, 24, 22, 22)
        side.setSpacing(12)
        side.addWidget(label("01   SOURCE", "section"))
        self.source_kind = QComboBox()
        self.source_kind.addItem("Negative scan", "negative")
        self.source_kind.addItem("Positive photo — SwinIR", "positive")
        side.addWidget(self.source_kind)
        self.browse_button = button("Choose image…", self.browse_file)
        side.addWidget(self.browse_button)
        self.filename = label("No image selected", wrap=True)
        side.addWidget(self.filename)
        self.metadata = label("Drag a TIFF or JPEG into the viewer.", "quiet", True)
        side.addWidget(self.metadata)
        side.addSpacing(14)
        side.addWidget(label("02   PROCESS", "section"))
        self.mode = QComboBox()
        for name, data in [("Both — compare results", "both"), ("FreeCCR", "freeccr"), ("darktable / Negadoctor", "negadoctor")]:
            self.mode.addItem(name, data)
        side.addWidget(self.mode)
        self.mode_note = label("Both creates two independent positives from the same negative.", "quiet", True)
        side.addWidget(self.mode_note)
        self.mode.currentIndexChanged.connect(self.mode_changed)
        self.convert_button = button("Convert negative", self.convert, True)
        self.convert_button.setEnabled(False)
        side.addWidget(self.convert_button)
        self.cancel_button = button("Cancel processing", self.cancel)
        self.cancel_button.hide()
        side.addWidget(self.cancel_button)
        self.advanced = QCheckBox("Negadoctor settings")
        self.advanced.toggled.connect(self.toggle_advanced)
        side.addWidget(self.advanced)
        self.settings_panel = QWidget()
        form = QVBoxLayout(self.settings_panel)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(10)
        self.encoding = QComboBox()
        self.encoding.addItem("Linear scanner RGB", "linear")
        self.encoding.addItem("sRGB-encoded scan / JPEG", "srgb")
        self.encoding.setToolTip("Explicit input assumption for Negadoctor. Use sRGB for JPEGs; choose the encoding of your TIFF scanner output.")
        form.addWidget(label("Input encoding", "quiet"))
        form.addWidget(self.encoding)
        self.sample_button = button("Sample clear film base", self.sample_base)
        form.addWidget(self.sample_button)
        self.base_note = label("Film base: automatic estimate", "quiet", True)
        form.addWidget(self.base_note)
        self.clear_base_button = button("Reset film-base estimate", self.clear_base)
        form.addWidget(self.clear_base_button)
        numeric = QFormLayout()
        self.grade = QDoubleSpinBox()
        self.grade.setRange(1, 8)
        self.grade.setSingleStep(.1)
        self.grade.setValue(3.3)
        self.exposure = QDoubleSpinBox()
        self.exposure.setRange(.5, 2)
        self.exposure.setSingleStep(.05)
        self.exposure.setValue(1.06)
        numeric.addRow("Paper grade", self.grade)
        numeric.addRow("Print exposure", self.exposure)
        form.addLayout(numeric)
        side.addWidget(self.settings_panel)
        self.settings_panel.hide()
        side.addSpacing(8)
        side.addWidget(label("03   SWINIR", "section"))
        self.upscale_button = button("Upscale selected result 2×", self.upscale_result)
        side.addWidget(self.upscale_button)
        side.addWidget(label("Optional · doubles width and height.\nUse a converted or existing positive.", "quiet", True))
        self.swinir_advanced = QCheckBox("SwinIR settings")
        side.addWidget(self.swinir_advanced)
        self.swinir_panel = QWidget()
        swinir_form = QFormLayout(self.swinir_panel)
        swinir_form.setContentsMargins(0, 0, 0, 0)
        self.swinir_device = QComboBox()
        self.swinir_device.addItem("NVIDIA GPU", "cuda")
        self.swinir_device.addItem("CPU", "cpu")
        self.swinir_tile = QComboBox()
        for size in (128, 256, 384):
            self.swinir_tile.addItem(str(size), size)
        self.swinir_tile.setCurrentIndex(1)
        self.swinir_tile.setToolTip("Smaller tiles reduce inference memory. Large images still require memory for the output.")
        swinir_form.addRow("Device", self.swinir_device)
        swinir_form.addRow("Tile size", self.swinir_tile)
        side.addWidget(self.swinir_panel)
        self.swinir_panel.hide()
        self.swinir_advanced.toggled.connect(self.swinir_panel.setVisible)
        side.addStretch()
        side.addWidget(label("04   EDIT", "section"))
        self.free_editor = button("Open negative in FreeCCR", lambda: self.open_editor("freeccr"))
        self.dark_editor = button("Edit negative in darktable", lambda: self.open_editor("negadoctor"))
        side.addWidget(self.free_editor)
        side.addWidget(self.dark_editor)
        side.addWidget(label("16-bit lossless TIFF results.\nOriginal scans are preserved.", "quiet", True))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setFixedWidth(305)
        scroll.setWidget(inspector)
        body.addWidget(scroll)
        workspace = QWidget()
        work = QVBoxLayout(workspace)
        work.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget()
        self.views = {}
        for key, name, empty in [("negative", "Negative", "Drop a negative here\nTIFF or JPEG · or click to browse"),
                                 ("freeccr", "FreeCCR", "The FreeCCR result will appear here"),
                                 ("negadoctor", "Negadoctor", "The Negadoctor result will appear here")]:
            view = ImageView(empty)
            view.dropped.connect(self.load_file)
            view.browse.connect(self.browse_file)
            self.views[key] = view
            self.tabs.addTab(view, name)
        self.views["negative"].sample.connect(self.base_sampled)
        compare = QSplitter(Qt.Horizontal)
        self.compare_views = {}
        for key, name in [("freeccr", "FreeCCR"), ("negadoctor", "darktable / Negadoctor")]:
            column = QWidget()
            column_layout = QVBoxLayout(column)
            column_layout.setContentsMargins(0, 15, 0, 0)
            title = label(name, "quiet")
            title.setAlignment(Qt.AlignCenter)
            column_layout.addWidget(title)
            view = ImageView("Waiting for conversion")
            view.dropped.connect(self.load_file)
            self.compare_views[key] = view
            column_layout.addWidget(view, 1)
            compare.addWidget(column)
        self.tabs.addTab(compare, "Compare")
        swinir_view = ImageView("The SwinIR enlargement will appear here")
        swinir_view.dropped.connect(self.load_file)
        swinir_view.browse.connect(self.browse_file)
        self.views["swinir"] = swinir_view
        self.tabs.addTab(swinir_view, "SwinIR 2×")
        self.tabs.currentChanged.connect(self.update_result_controls)
        work.addWidget(self.tabs, 1)
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(20, 10, 20, 12)
        self.result_info = label("Preview only · saved files keep full resolution", "quiet", True)
        toolbar.addWidget(self.result_info, 1)
        self.result_choice = QComboBox()
        self.result_choice.addItem("FreeCCR result", "freeccr")
        self.result_choice.addItem("Negadoctor result", "negadoctor")
        self.result_choice.addItem("SwinIR result", "swinir")
        self.result_choice.currentIndexChanged.connect(self.update_result_controls)
        toolbar.addWidget(self.result_choice)
        self.finish_button = button("Finish result in darktable", self.finish_result)
        toolbar.addWidget(self.finish_button)
        work.addLayout(toolbar)
        body.addWidget(workspace, 1)
        layout.addLayout(body, 1)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(3)
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        layout.addWidget(self.progress)
        footer = QHBoxLayout()
        footer.setContentsMargins(25, 12, 25, 12)
        self.status = label("Ready · choose an unconverted negative", "quiet", True)
        footer.addWidget(self.status, 1)
        self.folder_button = button("Open results folder", self.open_results)
        self.folder_button.setToolTip(str(RESULTS))
        self.folder_button.setEnabled(False)
        footer.addWidget(self.folder_button)
        layout.addLayout(footer)
        self.setCentralWidget(container)
        self.source_kind.currentIndexChanged.connect(self.source_kind_changed)
        self.refresh_controls()

    def toggle_advanced(self, checked):
        self.settings_panel.setVisible(checked and self.source_kind.currentData() == "negative")

    def source_kind_changed(self):
        negative = self.source_kind.currentData() == "negative"
        self.tabs.setTabText(0, "Negative" if negative else "Positive")
        self.views["negative"].empty = ("Drop a negative here" if negative else "Drop a positive here") + "\nTIFF or JPEG · or click to browse"
        self.views["negative"].update()
        self.mode.setVisible(negative)
        self.advanced.setVisible(negative)
        self.settings_panel.setVisible(negative and self.advanced.isChecked())
        self.convert_button.setText("Convert negative" if negative else "Upscale positive 2×")
        if not negative:
            self.views["negative"].sampling = False
            self.views["negative"].unsetCursor()
        self.mode_changed()
        self.refresh_controls()

    def mode_changed(self):
        if self.source_kind.currentData() == "positive":
            self.mode_note.setText("Run SwinIR on this positive when you choose. Negative conversion is skipped.")
            return
        notes = {"both": "Both creates two independent positives from the same negative.",
                 "freeccr": "Automatic reference conversion with the installed FreeCCR engine.",
                 "negadoctor": "Automatic starting settings rendered by darktable's Negadoctor module."}
        self.mode_note.setText(notes[self.mode.currentData()])

    def refresh_controls(self):
        loaded = self.source is not None
        ready = loaded and not self.busy
        negative = self.source_kind.currentData() == "negative"
        self.source_kind.setEnabled(not self.busy)
        self.browse_button.setEnabled(not self.busy)
        self.mode.setEnabled(not self.busy)
        self.settings_panel.setEnabled(not self.busy)
        self.advanced.setEnabled(not self.busy)
        self.convert_button.setEnabled(ready)
        self.free_editor.setEnabled(ready and negative)
        self.dark_editor.setEnabled(ready and negative)
        self.swinir_advanced.setEnabled(not self.busy)
        self.swinir_panel.setEnabled(not self.busy)
        self.cancel_button.setVisible(self.process is not None and self.process.state() != QProcess.NotRunning)
        self.folder_button.setEnabled(RESULTS.is_dir())
        for view in list(self.views.values()) + list(self.compare_views.values()):
            view.setAcceptDrops(not self.busy)
        self.sample_button.setEnabled(ready and negative)
        self.update_result_controls()

    def browse_file(self):
        if self.busy:
            return
        title = "Choose an unconverted negative" if self.source_kind.currentData() == "negative" else "Choose a positive to upscale"
        path, _ = QFileDialog.getOpenFileName(self, title, str(WORKSPACE), "Photos (*.tif *.tiff *.jpg *.jpeg)")
        if path:
            self.load_file(path)

    def load_file(self, path):
        if self.busy:
            return
        self.busy = True
        self.status.setText("Reading image preview…")
        self.progress.setRange(0, 0)
        self.refresh_controls()
        self.loader = PreviewLoader(path)
        self.loader.loaded.connect(self.file_loaded)
        self.loader.failed.connect(self.load_failed)
        self.loader.finished.connect(self.loader_finished)
        self.loader.start()

    def file_loaded(self, pixels, info):
        self.source = Path(info["path"])
        self.pixels, self.info = pixels, info
        self.results = {}
        self.job, self.report = None, None
        self.negative_report = None
        self.base_rgb = None
        self.clear_base()
        for view in self.views.values():
            view.clear()
        for view in self.compare_views.values():
            view.clear()
        self.views["negative"].set_pixels(pixels)
        self.filename.setText(self.source.name)
        self.filename.setToolTip(str(self.source))
        precision = f"{info['bits']} bits/channel"
        self.metadata.setText(f"{info['width']:,} × {info['height']:,} · {precision}")
        self.encoding.setCurrentIndex(1 if self.source.suffix.lower() in {".jpg", ".jpeg"} else 0)
        self.tabs.setCurrentIndex(0)
        action = "Ready to convert" if self.source_kind.currentData() == "negative" else "Ready for optional SwinIR upscaling"
        self.status.setText(action + (" · 8-bit input" if info["bits"] == 8 else " · 16-bit source"))

    def load_failed(self, message):
        self.status.setText(message)
        QMessageBox.warning(self, "Cannot load image", message)

    def loader_finished(self):
        self.busy = False
        self.progress.setRange(0, 1)
        self.loader.deleteLater()
        self.loader = None
        self.refresh_controls()
        if self.closing:
            self.close()

    def sample_base(self):
        self.tabs.setCurrentIndex(0)
        view = self.views["negative"]
        view.sampling = True
        view.setCursor(Qt.CrossCursor)
        self.status.setText("Click a clean area of clear, unexposed film beside the photograph.")

    def base_sampled(self, x, y):
        h, w = self.pixels.shape[:2]
        row, col = min(h - 1, int(y * h)), min(w - 1, int(x * w))
        patch = self.pixels[max(0, row - 3):min(h, row + 4), max(0, col - 3):min(w, col + 4)]
        base = np.median(patch.reshape(-1, 3), axis=0) / 65535
        if np.any(base <= 0):
            self.status.setText("That patch contains a zero channel. Choose clear film with light in every channel.")
            return
        self.base_rgb = base.tolist()
        self.base_note.setText("Sampled RGB: " + " / ".join(f"{value:.3f}" for value in base))
        view = self.views["negative"]
        view.sampling = False
        view.unsetCursor()
        self.status.setText("Film-base patch sampled. Convert again to apply it to Negadoctor.")

    def clear_base(self):
        self.base_rgb = None
        self.base_note.setText("Film base: automatic estimate")
        self.views["negative"].sampling = False
        self.views["negative"].last_sample = None
        self.views["negative"].unsetCursor()
        self.views["negative"].update()

    def convert(self):
        self.pending_editor = None
        self.start_job(self.mode.currentData() if self.source_kind.currentData() == "negative" else "swinir")

    def upscale_result(self):
        result = self.results.get(self.result_choice.currentData())
        if result and not self.busy:
            self.pending_editor = None
            self.start_job("swinir", source=Path(result["path"]))

    def start_job(self, mode, source=None):
        if self.busy or self.source is None:
            return
        self.job = new_job_path()
        self.current_mode = mode
        if mode != "swinir":
            self.results = {}
            self.negative_report = None
            for key in ("freeccr", "negadoctor", "swinir"):
                self.views[key].clear()
            for view in self.compare_views.values():
                view.clear()
        self.report, self.last_error = None, None
        self.busy = True
        self.buffer = ""
        self.decoder = codecs.getincrementaldecoder("utf-8")("replace")
        self.cancel_button.setEnabled(True)
        self.process = QProcess(self)
        env = QProcessEnvironment.systemEnvironment()
        runtime = HERE / "local-data"
        for key, directory in {"APPDATA": "appdata", "LOCALAPPDATA": "cache", "TEMP": "tmp", "TMP": "tmp",
                               "XDG_CACHE_HOME": "cache", "PYOPENCL_CACHE_DIR": "cache/opencl"}.items():
            target = runtime / directory
            target.mkdir(parents=True, exist_ok=True)
            env.insert(key, str(target))
        env.insert("PYTHONIOENCODING", "utf-8")
        self.process.setProcessEnvironment(env)
        self.process.setWorkingDirectory(str(HERE))
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.read_process)
        self.process.finished.connect(self.job_finished)
        self.process.errorOccurred.connect(self.process_error)
        args = [str(HERE / "engine.py"), str(source or self.source), "--engine", mode, "--job", str(self.job),
                "--output", str(RESULTS),
                "--encoding", self.encoding.currentData(), "--grade", str(self.grade.value()),
                "--exposure", str(self.exposure.value())]
        if self.base_rgb:
            args += ["--base-rgb", *map(str, self.base_rgb)]
        if mode == "prepare" and self.pending_editor:
            args += ["--prepare-editor", self.pending_editor]
        if mode == "swinir":
            args += ["--swinir-device", self.swinir_device.currentData(), "--swinir-tile", str(self.swinir_tile.currentData())]
        self.progress.setRange(0, 0)
        self.status.setText("Starting SwinIR…" if mode == "swinir" else "Preparing editor working copy…" if mode == "prepare" else "Starting conversion…")
        self.process.start(str(FREECCR / ".venv" / "Scripts" / "python.exe"), args)
        self.refresh_controls()

    def read_process(self):
        if self.process is None:
            return
        data = bytes(self.process.readAllStandardOutput())
        self.buffer += self.decoder.decode(data)
        lines = self.buffer.split("\n")
        self.buffer = lines.pop()
        for line in lines:
            try:
                event = json.loads(line)
            except (ValueError, TypeError):
                continue
            kind = event.get("event")
            if kind == "status":
                self.status.setText(event["message"])
            elif kind == "result":
                engine = event["engine"]
                self.results[engine] = event["result"]
                try:
                    self.views[engine].set_preview(event["result"]["preview"])
                    if engine in self.compare_views:
                        self.compare_views[engine].set_preview(event["result"]["preview"])
                except Exception as exc:
                    self.last_error = str(exc)
                if engine == "swinir":
                    self.tabs.setCurrentIndex(4)
                elif {"freeccr", "negadoctor"} <= self.results.keys():
                    self.tabs.setCurrentIndex(3)
                else:
                    self.tabs.setCurrentIndex(1 if engine == "freeccr" else 2)
                self.update_result_controls()
            elif kind in ("error", "engine_error"):
                self.last_error = event["message"]
                self.status.setText(event["message"])
            elif kind == "done":
                self.report = event["report"]
                if self.report.get("input_kind", "negative") == "negative":
                    self.negative_report = self.report

    def process_error(self, error):
        if error == QProcess.FailedToStart:
            self.last_error = "The local Python runtime could not start: " + self.process.errorString()
            self.job_finished(1, QProcess.NormalExit)

    def job_finished(self, code, exit_status):
        if self.process is None:
            return
        self.read_process()
        self.busy = False
        self.progress.setRange(0, 1)
        self.progress.setValue(1 if self.results else 0)
        self.process.deleteLater()
        self.process = None
        status = self.report.get("status") if self.report else "failed"
        count = len(self.report.get("results", {})) if self.report else 0
        messages = {"complete": f"Complete · {count} TIFF result(s) · source verified unchanged",
                    "partial": "One converter failed; the successful result is saved. " + (self.last_error or ""),
                    "failed": self.last_error or f"Conversion failed. Details: {self.job}",
                    "cancelled": "Cancelled · completed results are kept"}
        self.status.setText(messages.get(status, status))
        self.refresh_controls()
        if self.pending_editor and status == "complete":
            editor = self.pending_editor
            self.pending_editor = None
            self.launch_editor(editor, Path(self.report["negative"]))
        elif status in ("failed", "partial") and not self.closing:
            QMessageBox.warning(self, "Conversion needs attention", messages[status])
        if self.closing:
            self.close()

    def cancel(self):
        if self.process is None:
            return
        self.job.parent.mkdir(parents=True, exist_ok=True)
        self.job.with_suffix(".cancel").touch()
        self.cancel_button.setEnabled(False)
        self.status.setText("Cancelling after the current file operation…")

    def update_result_controls(self):
        index = self.tabs.currentIndex()
        if index in (1, 2):
            self.result_choice.setCurrentIndex(index - 1)
        elif index == 4:
            self.result_choice.setCurrentIndex(2)
        result = self.results.get(self.result_choice.currentData())
        self.result_choice.setEnabled(index == 3 and not self.busy)
        self.finish_button.setEnabled(bool(result) and not self.busy)
        self.upscale_button.setEnabled(bool(result) and not self.busy)
        if result:
            info = result["info"]
            self.result_info.setText(f"{info['width']:,} × {info['height']:,} · 16-bit TIFF · {result['seconds']:.1f}s")
            self.result_info.setToolTip(result["path"])
        else:
            self.result_info.setText("Preview only · saved files keep full resolution")

    def open_editor(self, editor):
        if self.busy or self.source_kind.currentData() != "negative":
            return
        if (self.negative_report and self.negative_report.get("negative") and Path(self.negative_report["negative"]).is_file()
                and (editor == "freeccr" or Path(self.negative_report["negative"] + ".xmp").is_file())):
            self.launch_editor(editor, Path(self.negative_report["negative"]))
        else:
            self.pending_editor = editor
            self.start_job("prepare")

    def launch_editor(self, editor, path):
        try:
            if editor == "freeccr":
                executable = FREECCR / ".venv" / "Scripts" / "pythonw.exe"
                if not executable.is_file():
                    raise FileNotFoundError(f"FreeCCR's Python runtime is missing: {executable}")
                subprocess.Popen([str(executable), str(FREECCR / "launch_local.py"), str(path)], cwd=str(FREECCR),
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            else:
                executable = DARKTABLE / "app" / "bin" / "darktable.exe"
                if not executable.is_file():
                    raise FileNotFoundError(f"darktable is missing: {executable}")
                runtime = self.job / "editor"
                config = runtime / "config"
                config.mkdir(parents=True, exist_ok=True)
                original_config = DARKTABLE / "local-data" / "config" / "darktablerc"
                if original_config.is_file() and not (config / "darktablerc").exists():
                    shutil.copyfile(original_config, config / "darktablerc")
                env = darktable_environment(runtime)
                subprocess.Popen([str(executable), "--configdir", config.as_posix(), "--cachedir", Path(env["XDG_CACHE_HOME"]).as_posix(),
                                  "--tmpdir", Path(env["TMP"]).as_posix(), "--library", (runtime / "library.db").as_posix(), path.as_posix()],
                                 env=env, cwd=str(DARKTABLE), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            self.status.setText(f"Opened working copy in {'FreeCCR' if editor == 'freeccr' else 'darktable'}")
        except Exception as exc:
            self.status.setText(str(exc))
            QMessageBox.warning(self, "Cannot open editor", str(exc))

    def finish_result(self):
        result = self.results.get(self.result_choice.currentData())
        if result:
            self.launch_editor("negadoctor", Path(result["path"]))

    def open_results(self):
        if RESULTS.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(RESULTS)))

    def closeEvent(self, event):
        if self.busy:
            self.closing = True
            if self.process:
                self.cancel()
            event.ignore()
        else:
            event.accept()


def main():
    app = QApplication(sys.argv)
    configure_application(app)
    window = MainWindow()
    window.show()
    if len(sys.argv) > 1:
        window.load_file(sys.argv[1])
    return app.exec()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        log = HERE / "local-data" / "startup-error.txt"
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(traceback.format_exc(), encoding="utf-8")
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, f"NegativeLab could not start. Details:\n{log}", "NegativeLab", 0x10)
        raise
