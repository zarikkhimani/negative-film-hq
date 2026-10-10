"""Local negative conversion jobs. FreeCCR is imported; Negadoctor runs in darktable."""
from __future__ import annotations

import argparse
import hashlib
from fractions import Fraction
import json
import math
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import time
import traceback
import uuid
import xml.etree.ElementTree as ET

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import cv2
import imagecodecs
import numpy as np
from PIL import Image
import tifffile

HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parent
FREECCR = WORKSPACE / "FreeCCR"
DARKTABLE = WORKSPACE / "darktable"
SWINIR = WORKSPACE / "SwinIR"
RESULTS = HERE / "Results"
SWINIR_MODEL = SWINIR / "model_zoo" / "swinir" / "001_classicalSR_DF2K_s64w8_SwinIR-M_x2.pth"
SUPPORTED = {".tif", ".tiff", ".jpg", ".jpeg"}
DT_NS = "{http://darktable.sf.net/}"
RDF_NS = "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}"
for prefix, uri in {"x": "adobe:ns:meta/", "rdf": RDF_NS[1:-1], "darktable": DT_NS[1:-1]}.items():
    ET.register_namespace(prefix, uri)


class Cancelled(Exception):
    pass


def emit(kind, **values):
    print(json.dumps({"event": kind, **values}, ensure_ascii=False), flush=True)


def check_cancel(job):
    if (job / "cancel.flag").exists() or job.with_suffix(".cancel").exists():
        raise Cancelled("Conversion cancelled. Completed files are kept.")


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def orient(pixels, orientation):
    if orientation == 2:
        return pixels[:, ::-1]
    if orientation == 3:
        return pixels[::-1, ::-1]
    if orientation == 4:
        return pixels[::-1]
    if orientation == 5:
        return pixels.transpose(1, 0, 2)
    if orientation == 6:
        return np.rot90(pixels, 3)
    if orientation == 7:
        return pixels.transpose(1, 0, 2)[::-1, ::-1]
    if orientation == 8:
        return np.rot90(pixels, 1)
    return pixels


def _rational(value):
    return float(value[0]) / float(value[1]) if isinstance(value, tuple) else float(value)


def inspect_image(path):
    path = Path(path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Image does not exist: {path}")
    if path.suffix.lower() not in SUPPORTED:
        raise ValueError("Choose a TIFF or JPEG negative.")
    if path.suffix.lower() in {".tif", ".tiff"}:
        with tifffile.TiffFile(path) as tf:
            if any(not page.is_reduced and not (int(page.subfiletype) & 4) for page in list(tf.pages)[1:]):
                raise ValueError("Multi-page TIFFs are unsupported. Choose a single negative frame.")
            page = tf.pages[0]
            if page.photometric != 2 or page.samplesperpixel != 3 or page.dtype not in (np.dtype("uint8"), np.dtype("uint16")):
                raise ValueError("TIFF input must be unsigned 8- or 16-bit RGB with three channels.")
            orientation = int(page.tags[274].value) if 274 in page.tags else 1
            if orientation not in range(1, 9):
                raise ValueError("Unsupported TIFF orientation.")
            dpi = None
            if 282 in page.tags and 283 in page.tags:
                unit = int(page.tags[296].value) if 296 in page.tags else 1
                if unit in (2, 3):
                    factor = 2.54 if unit == 3 else 1
                    dpi = [_rational(page.tags[282].value) * factor, _rational(page.tags[283].value) * factor]
            info = dict(width=page.imagewidth, height=page.imagelength, bits=page.bitspersample,
                        orientation=orientation, dpi=dpi, embedded_icc=34675 in page.tags,
                        ancillary_pages=len(tf.pages) - 1)
    else:
        with Image.open(path) as image:
            if image.mode != "RGB":
                raise ValueError("JPEG input must be RGB. CMYK and grayscale are unsupported.")
            info = dict(width=image.width, height=image.height, bits=8,
                        orientation=int(image.getexif().get(274, 1)),
                        dpi=list(image.info["dpi"]) if "dpi" in image.info else None,
                        embedded_icc=bool(image.info.get("icc_profile")))
    if info["orientation"] in (5, 6, 7, 8):
        info["width"], info["height"] = info["height"], info["width"]
        if info["dpi"]:
            info["dpi"] = info["dpi"][::-1]
    info["path"] = str(path)
    return info


def read_preview(path, max_side=1200):
    """Decode TIFF strips/tiles one at a time; retain only a bounded RGB sample."""
    path = Path(path)
    info = inspect_image(path)
    if path.suffix.lower() in {".tif", ".tiff"}:
        with tifffile.TiffFile(path) as tf:
            page = tf.pages[0]
            step = max(1, math.ceil(max(page.imagewidth, page.imagelength) / max_side))
            sampled = np.zeros((math.ceil(page.imagelength / step), math.ceil(page.imagewidth / step), 3), dtype=page.dtype)
            for data, index, shape in page.segments(maxworkers=1):
                if data is None:
                    raise ValueError("Sparse TIFF segments are unsupported.")
                plane, _, row, col, _ = index
                block = data[0]
                h = min(block.shape[0], page.imagelength - row)
                w = min(block.shape[1], page.imagewidth - col)
                y0, x0 = (-row) % step, (-col) % step
                yy, xx = (row + y0) // step, (col + x0) // step
                part = block[y0:h:step, x0:w:step]
                if page.planarconfig == 2:
                    sampled[yy:yy + part.shape[0], xx:xx + part.shape[1], plane] = part[..., 0]
                else:
                    sampled[yy:yy + part.shape[0], xx:xx + part.shape[1]] = part
            if sampled.dtype == np.uint8:
                sampled = sampled.astype(np.uint16) * 257
    else:
        with Image.open(path) as image:
            image.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
            sampled = np.asarray(image).astype(np.uint16) * 257
    sampled = np.ascontiguousarray(orient(sampled, info["orientation"]))
    return sampled, info


def _tiff_rows(array, job, convert=None, rows=128):
    for row in range(0, array.shape[0], rows):
        check_cancel(job)
        block = np.ascontiguousarray(array[row:row + rows])
        if block.dtype == np.uint8:
            block = block.astype(np.uint16) * 257
        rendered = convert(block) if convert else block
        # tifffile accepts pre-compressed strip bytes; ndarray iterators represent whole pages.
        yield imagecodecs.zlib_encode(np.ascontiguousarray(rendered, dtype="<u2").tobytes())


def write_tiff(path, array, job, icc=None, dpi=None, convert=None):
    temp = path.with_name(path.stem + ".partial.tif")
    options = dict(shape=array.shape, dtype=np.uint16, photometric="rgb", compression="deflate",
                   rowsperstrip=128, metadata=None, byteorder="<", bigtiff=array.size * 2 > 3_500_000_000)
    if icc:
        options["iccprofile"] = icc
    if dpi:
        options.update(resolution=dpi, resolutionunit="INCH")
    try:
        tifffile.imwrite(temp, _tiff_rows(array, job, convert), **options)
        check_cancel(job)
        if path.exists():
            raise FileExistsError(f"Refusing to replace an existing output: {path}")
        temp.rename(path)
    finally:
        temp.unlink(missing_ok=True)


def prepare_image(source, job, info, stem="negative"):
    """Keep a byte-identical source copy, then bake orientation into a 16-bit TIFF."""
    snapshot = job / ("source" + source.suffix.lower())
    digest = hashlib.sha256()
    with source.open("rb") as src, snapshot.open("xb") as dst:
        for block in iter(lambda: src.read(4 * 1024 * 1024), b""):
            check_cancel(job)
            dst.write(block)
            digest.update(block)
    if source.suffix.lower() in {".tif", ".tiff"}:
        with tifffile.TiffFile(snapshot) as tf:
            page = tf.pages[0]
            array = page.asarray(out=str(job / "decode.tmp"), maxworkers=1)
            icc = page.tags[34675].value if 34675 in page.tags else None
            if page.planarconfig == 2:
                array = np.moveaxis(array, 0, -1)
    else:
        with Image.open(snapshot) as image:
            array = np.asarray(image)
            icc = image.info.get("icc_profile")
    array = orient(array, info["orientation"])
    negative = job / f"{stem}.tif"
    try:
        write_tiff(negative, array, job, icc=icc, dpi=info["dpi"])
    finally:
        # Close the memmap through any transpose/slice view before removing it on Windows.
        root = array
        while getattr(root, "base", None) is not None and not isinstance(root, np.memmap):
            root = root.base
        if isinstance(root, np.memmap):
            root._mmap.close()
        del array
        (job / "decode.tmp").unlink(missing_ok=True)
    return negative, digest.hexdigest()


def prepare_negative(source, job, info):
    return prepare_image(source, job, info)


def save_preview(path):
    sampled, _ = read_preview(path)
    preview = path.with_suffix(".jpg")
    Image.fromarray((sampled // 257).astype(np.uint8)).save(preview, quality=94, subsampling=0)
    return preview


def publish_result(output, preview, source, engine, results_dir):
    """Save a TIFF/JPEG pair in the shared folder without replacing either file."""
    results_dir = Path(results_dir).resolve()
    results_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{Path(source).stem}_{'swinir-x2' if engine == 'swinir' else engine}"
    number = 1
    while True:
        name = stem if number == 1 else f"{stem}_{number}"
        target = results_dir / f"{name}.tif"
        thumbnail = results_dir / f"{name}.jpg"
        created = []
        streams = []
        try:
            for path in (target, thumbnail):
                streams.append(path.open("xb"))
                created.append(path)
        except FileExistsError:
            for stream in streams:
                stream.close()
            for path in created:
                path.unlink()
            number += 1
            continue
        except Exception:
            for stream in streams:
                stream.close()
            for path in created:
                path.unlink()
            raise
        try:
            for original, destination in zip((output, preview), streams):
                with Path(original).open("rb") as src:
                    shutil.copyfileobj(src, destination, length=4 * 1024 * 1024)
        except Exception:
            for stream in streams:
                stream.close()
            for path in created:
                path.unlink()
            raise
        finally:
            for stream in streams:
                stream.close()
        return target, thumbnail


def run_freeccr(negative, job, info):
    sys.path.insert(0, str(FREECCR / "src"))
    from core.ccr_processor import compute_reference_norm_params, apply_reference_normalization
    from core.color_management import export_icc_bytes
    reference, _ = read_preview(negative, 1080)
    h, w = reference.shape[:2]
    # A narrow inset excludes edge dust. This determines anchors, never crops the output.
    x, y = max(0, int(w * .02)), max(0, int(h * .02))
    rect = (x, y, w - x, h - y)
    pixels = reference[y:h - y, x:w - x].reshape(-1, 3)
    if np.any(np.percentile(pixels, 99, axis=0) - np.percentile(pixels, 1, axis=0) < 16):
        raise ValueError("FreeCCR needs tonal variation in all three channels. Choose a complete negative frame.")
    lo, hi, factors = compute_reference_norm_params(reference, rect, 0)
    if not np.isfinite(np.concatenate([lo, hi, factors])).all():
        raise ValueError("FreeCCR could not calculate finite conversion parameters.")
    output = job / "freeccr.tif"
    with tifffile.TiffFile(negative) as tf:
        array = tf.pages[0].asarray(out=str(job / "freeccr-decode.tmp"), maxworkers=1)
    try:
        write_tiff(output, array, job, icc=export_icc_bytes("srgb"), dpi=info["dpi"],
                   convert=lambda block: apply_reference_normalization(block, lo, hi, factors))
    finally:
        array._mmap.close()
        (job / "freeccr-decode.tmp").unlink(missing_ok=True)
    return output, dict(method="FreeCCR reference normalization", reference_rect=list(rect),
                        reference_size=[w, h], percentile_low=lo.tolist(), percentile_high=hi.tolist(),
                        optical_density_factors=factors.tolist(), input_profile="Unmodified scanner RGB values",
                        auto_crop=False, auto_rotation=False)


def estimate_negadoctor(reference, encoding="linear", base_rgb=None, grade=3.3, exposure=1.06):
    pixels = reference.reshape(-1, 3).astype(np.float64) / 65535
    if encoding == "srgb":
        pixels = np.where(pixels <= .04045, pixels / 12.92, ((pixels + .055) / 1.055) ** 2.4)
    if base_rgb is not None:
        base = np.asarray(base_rgb, dtype=np.float64)
        if base.shape != (3,) or not np.isfinite(base).all() or np.any(base <= 0) or np.any(base > 1):
            raise ValueError("The sampled film base must contain three RGB values between zero and one.")
        if encoding == "srgb":
            base = np.where(base <= .04045, base / 12.92, ((base + .055) / 1.055) ** 2.4)
    else:
        base = np.minimum(np.percentile(pixels, 99.9, axis=0) * 1.05, 1.5)
    low = np.maximum(np.percentile(pixels, .1, axis=0), 1e-6)
    high = np.maximum(np.percentile(pixels, 99.9, axis=0), 1e-6)
    ranges = np.log10(high / low)
    if np.any(ranges < .01):
        raise ValueError("Negadoctor needs tonal variation in all three channels. Choose a complete negative frame.")
    dmax = float(np.clip(ranges.max(), .1, 6))
    wb = np.clip(dmax / ranges, .25, 2)
    offset = float(np.clip(np.min(np.log10(np.maximum(base, 1e-6) / high)) / dmax, -1, 1))
    if not 1 <= grade <= 8 or not .5 <= exposure <= 2:
        raise ValueError("Negadoctor paper grade or print exposure is out of range.")
    values = [*base, 1., *wb, 1., 1., 1., 1., 1., dmax, offset, .005, grade, .85, exposure]
    return struct.pack("<i18f", 1, *values), dict(
        film_base_method="Sampled patch" if base_rgb is not None else "99.9th percentile plus 5%; estimate",
        film_base_rgb=base.tolist(), Dmax=dmax, wb_high=wb.tolist(), offset=offset,
        paper_grade=grade, print_exposure=exposure, input_encoding=encoding,
        input_profile="linear Rec.709" if encoding == "linear" else "sRGB",
        working_profile="linear Rec.709", quality="Automatic starting point; refine in darktable")


def write_negadoctor_xmp(path, params, encoding):
    template = HERE / "resources" / "negadoctor-template.xmp"
    tree = ET.parse(template)
    entries = tree.findall(f".//{RDF_NS}li")
    for item in entries:
        operation = item.get(DT_NS + "operation")
        data = bytes.fromhex(item.get(DT_NS + "params", ""))
        if operation == "colorin":
            if len(data) != 1044 or item.get(DT_NS + "modversion") != "7":
                raise ValueError("Unsupported darktable input-profile template version.")
            data = struct.pack("<i", 3 if encoding == "linear" else 1) + data[4:]
            data = data[:528] + struct.pack("<i", 3) + data[532:]
        elif operation == "flip":
            data = struct.pack("<i", 0)  # Pixels in negative.tif are already oriented.
        elif operation == "negadoctor":
            if item.get(DT_NS + "modversion") != "2" or len(params) != 76:
                raise ValueError("Unsupported Negadoctor parameter layout.")
            data = params
        item.set(DT_NS + "params", data.hex())
    if not any(item.get(DT_NS + "operation") == "negadoctor" for item in entries):
        raise ValueError("The template has no Negadoctor module.")
    tree.write(path, encoding="utf-8", xml_declaration=True)


def darktable_environment(job):
    env = os.environ.copy()
    for key, folder in {"APPDATA": "appdata", "LOCALAPPDATA": "localappdata", "XDG_CACHE_HOME": "cache",
                        "CUDA_CACHE_PATH": "cache/nvidia", "TEMP": "tmp", "TMP": "tmp"}.items():
        target = job / "runtime" / folder
        target.mkdir(parents=True, exist_ok=True)
        env[key] = str(target)
    # Reuse compiled kernels between jobs; each catalog and config remains independent.
    for key, folder in {"XDG_CACHE_HOME": "darktable-cache", "CUDA_CACHE_PATH": "nvidia-cache"}.items():
        target = HERE / "local-data" / folder
        target.mkdir(parents=True, exist_ok=True)
        env[key] = str(target)
    return env


def preserve_dpi(output, dpi):
    if not dpi:
        return
    # Update existing TIFF tags in place, without decoding or re-encoding any pixels.
    with tifffile.TiffFile(output, mode="r+") as tf:
        tags = tf.pages[0].tags
        if any(code not in tags for code in (282, 283, 296)):
            raise ValueError("darktable output lacks resolution tags required to preserve scan DPI.")
        for code, value in zip((282, 283), dpi):
            rational = Fraction(value).limit_denominator(1_000_000)
            tags[code].overwrite((rational.numerator, rational.denominator))
        tags[296].overwrite(2)


def run_negadoctor(negative, job, options):
    executable = DARKTABLE / "app" / "bin" / "darktable-cli.exe"
    if not executable.is_file():
        raise FileNotFoundError(f"darktable-cli is missing: {executable}")
    reference, _ = read_preview(negative)
    params, settings = estimate_negadoctor(reference, options["encoding"], options.get("base_rgb"),
                                          options["grade"], options["exposure"])
    xmp = negative.with_suffix(".tif.xmp")
    write_negadoctor_xmp(xmp, params, options["encoding"])
    config = job / "runtime" / "config"
    config.mkdir(parents=True, exist_ok=True)
    original_config = DARKTABLE / "local-data" / "config" / "darktablerc"
    if original_config.is_file():
        shutil.copyfile(original_config, config / "darktablerc")
    output = job / "negadoctor.tif"
    partial = job / "negadoctor.partial.tif"
    env = darktable_environment(job)
    command = [str(executable), negative.as_posix(), xmp.as_posix(), partial.as_posix(), "--icc-type", "SRGB",
               "--apply-custom-presets", "false", "--core", "--configdir", config.as_posix(),
               "--cachedir", Path(env["XDG_CACHE_HOME"]).as_posix(), "--tmpdir", Path(env["TMP"]).as_posix(), "--library", ":memory:",
               "--conf", "write_sidecar_files=never", "--conf", "plugins/imageio/format/tiff/bpp=16",
               "--conf", "plugins/imageio/format/tiff/compress=2", "-d", "perf", "-d", "opencl"]
    log_path = job / "negadoctor.log"
    process = None
    try:
        with log_path.open("w", encoding="utf-8") as log:
            process = subprocess.Popen(command, env=env, cwd=str(DARKTABLE), stdout=log, stderr=subprocess.STDOUT,
                                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            while process.poll() is None:
                check_cancel(job)
                time.sleep(.2)
            if process.returncode:
                raise RuntimeError(f"darktable export failed (exit {process.returncode}). Details: {log_path}")
        check_cancel(job)
        if not partial.is_file():
            raise RuntimeError(f"darktable did not create its TIFF. Details: {log_path}")
        preserve_dpi(partial, inspect_image(negative)["dpi"])
        result_info = inspect_image(partial)
        if result_info["bits"] != 16:
            raise RuntimeError("darktable did not produce a 16-bit TIFF.")
        partial.rename(output)
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        partial.unlink(missing_ok=True)
    settings["xmp"] = str(xmp)
    settings["log"] = str(log_path)
    return output, settings


def validate_swinir_options(options):
    device = options.get("swinir_device", "cuda")
    tile = options.get("swinir_tile", 256)
    if device not in ("cuda", "cpu"):
        raise ValueError("SwinIR device must be cuda or cpu.")
    if not isinstance(tile, int) or tile < 64 or tile % 8:
        raise ValueError("SwinIR tile size must be a multiple of 8, at least 64 pixels.")
    return device, tile


def run_swinir(positive, job, info, options):
    """Run the existing x2 tool in its own environment, then restore metadata losslessly."""
    device, tile = validate_swinir_options(options)
    executable = SWINIR / ".venv" / "Scripts" / "python.exe"
    runner = SWINIR / "upscale_x2.py"
    for path in (executable, runner, SWINIR_MODEL):
        if not path.is_file():
            raise FileNotFoundError(f"SwinIR component is missing: {path}")
    work = job / "swinir-work"
    work.mkdir()
    raw_output = work / f"{positive.stem}_SwinIR_x2.tif"
    log_path = job / "swinir.log"
    command = [str(executable), "-u", str(runner), str(positive), "--output", str(work),
               "--format", "tiff", "--device", device, "--tile", str(tile), "--tile-overlap", "32"]
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["TORCH_HOME"] = str(HERE / "local-data" / "torch")
    env["CUDA_CACHE_PATH"] = str(HERE / "local-data" / "nvidia-cache")
    process = None
    try:
        with log_path.open("w", encoding="utf-8") as log:
            process = subprocess.Popen(command, env=env, cwd=str(SWINIR), stdout=log,
                                       stderr=subprocess.STDOUT, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            while process.poll() is None:
                check_cancel(job)
                time.sleep(.2)
            if process.returncode:
                detail = log_path.read_text(encoding="utf-8", errors="replace").strip().splitlines()
                tail = detail[-1] if detail else "No diagnostic output."
                raise RuntimeError(f"SwinIR failed (exit {process.returncode}): {tail}\nDetails: {log_path}")
        check_cancel(job)
        if not raw_output.is_file():
            raise RuntimeError(f"SwinIR did not create its TIFF. Details: {log_path}")
        raw_info = inspect_image(raw_output)
        if (raw_info["width"], raw_info["height"], raw_info["bits"]) != (info["width"] * 2, info["height"] * 2, 16):
            raise ValueError("SwinIR output must have twice the width/height and 16-bit RGB samples.")
        emit("status", message="Saving SwinIR TIFF with the source color profile and DPI…")
        with tifffile.TiffFile(positive) as tf:
            icc = tf.pages[0].tags[34675].value if 34675 in tf.pages[0].tags else None
        with tifffile.TiffFile(raw_output) as tf:
            array = tf.pages[0].asarray(out=str(job / "swinir-decode.tmp"), maxworkers=1)
        output = job / "swinir-x2.tif"
        try:
            write_tiff(output, array, job, icc=icc, dpi=info["dpi"])
        finally:
            array._mmap.close()
            (job / "swinir-decode.tmp").unlink(missing_ok=True)
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        raw_output.unlink(missing_ok=True)
    return output, dict(method="SwinIR Classical SR x2", scale=2, device=device, tile=tile, tile_overlap=32,
                        model=str(SWINIR_MODEL), model_sha256=sha256(SWINIR_MODEL), log=str(log_path),
                        input_kind="positive", source_profile_preserved=bool(icc), source_dpi_preserved=bool(info["dpi"]))


def run_job(source, engines, options, job, results_dir=None):
    job = Path(job).resolve()
    results_dir = Path(results_dir or RESULTS).resolve()
    if job.exists():
        raise FileExistsError("Job folder already exists. Start a new conversion to preserve earlier files.")
    job.mkdir(parents=True)
    source = Path(source).resolve()
    info = inspect_image(source)
    is_upscale = engines == ["swinir"]
    if "swinir" in engines and not is_upscale:
        raise ValueError("SwinIR processes a positive in a separate job after negative conversion.")
    if is_upscale:
        validate_swinir_options(options)
    required = source.stat().st_size + info["width"] * info["height"] * 6 * (16 if is_upscale else 4 + len(engines))
    if shutil.disk_usage(job).free < required:
        raise OSError(f"Allow at least {required / 1024**3:.1f} GB free space for this conversion.")
    report = dict(source=str(source), input=info, engines=engines, options=options, results={}, errors={},
                  results_dir=str(results_dir),
                  input_kind="positive" if is_upscale else "negative",
                  status="running", created=time.strftime("%Y-%m-%d %H:%M:%S"))
    manifest = job / "job.json"

    def record():
        manifest.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    try:
        check_cancel(job)
        emit("status", message="Preparing a protected working copy…")
        negative, digest = prepare_image(source, job, info, "positive" if is_upscale else "negative")
        report["positive" if is_upscale else "negative"] = str(negative)
        report["source_sha256"] = digest
        if not engines and options.get("prepare_editor", "negadoctor") == "negadoctor":
            reference, _ = read_preview(negative)
            params, settings = estimate_negadoctor(reference, options["encoding"], options.get("base_rgb"),
                                                  options["grade"], options["exposure"])
            write_negadoctor_xmp(negative.with_suffix(".tif.xmp"), params, options["encoding"])
            report["negadoctor_starting_settings"] = settings
        record()
        for engine in engines:
            check_cancel(job)
            emit("status", message=(f"Upscaling with SwinIR: {info['width']:,} × {info['height']:,} → {info['width'] * 2:,} × {info['height'] * 2:,}…"
                                    if engine == "swinir" else f"Converting with {'FreeCCR' if engine == 'freeccr' else 'darktable / Negadoctor'}…"))
            started = time.perf_counter()
            try:
                if engine == "freeccr":
                    output, settings = run_freeccr(negative, job, info)
                elif engine == "negadoctor":
                    output, settings = run_negadoctor(negative, job, options)
                elif engine == "swinir":
                    output, settings = run_swinir(negative, job, info, options)
                else:
                    raise ValueError(f"Unknown converter: {engine}")
                result_info = inspect_image(output)
                scale = 2 if engine == "swinir" else 1
                if (result_info["width"], result_info["height"], result_info["bits"]) != (info["width"] * scale, info["height"] * scale, 16):
                    raise ValueError("Output dimensions or TIFF precision did not match the source.")
                check_cancel(job)
                preview = save_preview(output)
                working_output, working_preview = output, preview
                output, preview = publish_result(output, preview, source, engine, results_dir)
                result_info["path"] = str(output)
                result = dict(path=str(output), preview=str(preview), settings=settings,
                              seconds=round(time.perf_counter() - started, 2), info=result_info)
                report["results"][engine] = result
                record()
                emit("result", engine=engine, result=result)
                working_output.unlink()
                working_preview.unlink()
            except Cancelled:
                raise
            except Exception as exc:
                report["errors"][engine] = str(exc)
                (job / f"{engine}-error.txt").write_text(traceback.format_exc(), encoding="utf-8")
                record()
                emit("engine_error", engine=engine, message=str(exc))
        emit("status", message="Verifying the original file…")
        report["original_preserved"] = sha256(source) == digest
        if not report["original_preserved"]:
            raise RuntimeError(f"The source file changed during the job. The captured source copy is kept in {job}.")
        report["status"] = "complete" if not report["errors"] else "partial" if report["results"] else "failed"
    except Cancelled as exc:
        report["status"] = "cancelled"
        report["message"] = str(exc)
    except Exception as exc:
        report["status"] = "failed"
        report["message"] = str(exc)
        (job / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")
        emit("error", message=str(exc))
    finally:
        record()
        job.with_suffix(".cancel").unlink(missing_ok=True)
    emit("done", status=report["status"], job=str(job), report=report)
    return report


def new_job_path(root=None):
    return Path(root or HERE / "local-data" / "jobs") / (time.strftime("%Y-%m-%d_%H%M%S_") + uuid.uuid4().hex[:8])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--engine", choices=["freeccr", "negadoctor", "both", "prepare", "swinir"], default="both")
    parser.add_argument("--encoding", choices=["linear", "srgb"], default="linear")
    parser.add_argument("--grade", type=float, default=3.3)
    parser.add_argument("--exposure", type=float, default=1.06)
    parser.add_argument("--base-rgb", nargs=3, type=float)
    parser.add_argument("--prepare-editor", choices=["freeccr", "negadoctor"], default="negadoctor")
    parser.add_argument("--job", type=Path, help="Internal working folder; must not already exist")
    parser.add_argument("--output", type=Path, default=RESULTS, help="Shared folder for converted TIFFs and JPEG previews")
    parser.add_argument("--swinir-device", choices=["cuda", "cpu"], default="cuda")
    parser.add_argument("--swinir-tile", type=int, default=256)
    args = parser.parse_args()
    engines = ["freeccr", "negadoctor"] if args.engine == "both" else [] if args.engine == "prepare" else [args.engine]
    options = dict(encoding=args.encoding, grade=args.grade, exposure=args.exposure, base_rgb=args.base_rgb,
                   prepare_editor=args.prepare_editor, swinir_device=args.swinir_device, swinir_tile=args.swinir_tile)
    report = run_job(args.source, engines, options, args.job or new_job_path(), args.output)
    return 0 if report["status"] == "complete" else 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        emit("error", message=str(exc))
        sys.exit(1)
