import sys
from pathlib import Path
import struct
import xml.etree.ElementTree as ET

import numpy as np
import pytest
import tifffile
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import engine


def negative(h=129, w=163):
    y, x = np.mgrid[:h, :w]
    field = (x / w * .6 + y / h * .4)
    return np.stack([8000 + field * 46000, 4000 + field * 33000,
                     2000 + field * 23000], axis=-1).astype(np.uint16)


@pytest.mark.parametrize("layout", ["strips", "tiles", "planar"])
@pytest.mark.parametrize("orientation", [1, 2, 3, 4, 5, 6, 7, 8])
def test_bounded_preview_matches_pixels(tmp_path, layout, orientation):
    pixels = negative()
    path = tmp_path / "scan.tif"
    args = dict(photometric="rgb", compression="deflate", extratags=[(274, "H", 1, orientation, False)])
    if layout == "tiles":
        args["tile"] = (32, 32)
    elif layout == "planar":
        pixels = pixels.transpose(2, 0, 1)
        args["planarconfig"] = "separate"
    else:
        args["rowsperstrip"] = 17
    tifffile.imwrite(path, pixels, **args)
    preview, info = engine.read_preview(path, 60)
    step = 3
    expected = engine.orient(negative()[::step, ::step], orientation)
    np.testing.assert_array_equal(preview, expected)
    assert max(preview.shape[:2]) <= 60
    if orientation in (5, 6, 7, 8):
        assert (info["width"], info["height"]) == (129, 163)


def test_working_copy_is_lossless_and_oriented(tmp_path):
    source = tmp_path / "源 scan.tif"
    pixels = negative()
    tifffile.imwrite(source, pixels, photometric="rgb", compression="lzw", resolution=(4800, 9600),
                     resolutionunit="INCH", extratags=[(274, "H", 1, 6, False)])
    digest = engine.sha256(source)
    job = tmp_path / "job"
    job.mkdir()
    info = engine.inspect_image(source)
    copy, saved_hash = engine.prepare_negative(source, job, info)
    np.testing.assert_array_equal(tifffile.imread(copy), np.rot90(pixels, 3))
    assert saved_hash == digest == engine.sha256(source) == engine.sha256(job / "source.tif")
    assert engine.inspect_image(copy)["dpi"] == [9600, 4800]
    assert not (job / "decode.tmp").exists()


def test_freeccr_chunks_match_full_engine(tmp_path):
    source = tmp_path / "negative.tif"
    pixels = negative(301, 163)
    tifffile.imwrite(source, pixels, photometric="rgb", resolution=(4800, 4800), resolutionunit="INCH")
    job = tmp_path / "job"
    job.mkdir()
    output, settings = engine.run_freeccr(source, job, engine.inspect_image(source))
    from core.ccr_processor import compute_reference_norm_params, apply_reference_normalization
    ref, _ = engine.read_preview(source, 1080)
    lo, hi, factors = compute_reference_norm_params(ref, tuple(settings["reference_rect"]), 0)
    expected = apply_reference_normalization(pixels, lo, hi, factors)
    actual = tifffile.imread(output)
    np.testing.assert_array_equal(actual, expected)
    with tifffile.TiffFile(output) as tf:
        assert tf.pages[0].bitspersample == 16
        assert 34675 in tf.pages[0].tags
        assert tf.pages[0].compression != 1
    assert engine.inspect_image(output)["dpi"] == [4800, 4800]


def test_flat_negative_fails_clearly(tmp_path):
    path = tmp_path / "flat.tif"
    tifffile.imwrite(path, np.full((30, 30, 3), 10000, np.uint16), photometric="rgb")
    with pytest.raises(ValueError, match="tonal variation"):
        engine.run_freeccr(path, tmp_path, engine.inspect_image(path))
    with pytest.raises(ValueError, match="tonal variation"):
        engine.estimate_negadoctor(np.full((30, 30, 3), 10000, np.uint16))


def test_reject_multipage_and_grayscale(tmp_path):
    path = tmp_path / "gray.tif"
    tifffile.imwrite(path, np.zeros((20, 30), np.uint16))
    with pytest.raises(ValueError, match="RGB"):
        engine.inspect_image(path)
    path = tmp_path / "pages.tif"
    with tifffile.TiffWriter(path) as writer:
        writer.write(negative(), photometric="rgb")
        writer.write(negative(), photometric="rgb")
    with pytest.raises(ValueError, match="Multi-page"):
        engine.inspect_image(path)


def test_jpeg_precision_is_reported(tmp_path):
    path = tmp_path / "scan.jpg"
    Image.fromarray((negative() // 257).astype(np.uint8)).save(path)
    pixels, info = engine.read_preview(path)
    assert info["bits"] == 8 and pixels.dtype == np.uint16


def test_negadoctor_profile_and_sample_written(tmp_path):
    params, settings = engine.estimate_negadoctor(negative(), "srgb", [.85, .6, .4], 3.5, 1.1)
    path = tmp_path / "negative.tif.xmp"
    engine.write_negadoctor_xmp(path, params, "srgb")
    entries = ET.parse(path).findall(f".//{engine.RDF_NS}li")
    ops = {e.get(engine.DT_NS + "operation"): e for e in entries}
    colorin = bytes.fromhex(ops["colorin"].get(engine.DT_NS + "params"))
    assert struct.unpack_from("<i", colorin)[0] == 1
    assert struct.unpack_from("<i", colorin, 528)[0] == 3
    assert bytes.fromhex(ops["negadoctor"].get(engine.DT_NS + "params")) == params
    assert settings["film_base_method"] == "Sampled patch"
    assert len(params) == 76


def test_cancel_before_start_preserves_source(tmp_path):
    source = tmp_path / "scan.tif"
    tifffile.imwrite(source, negative(), photometric="rgb")
    digest = engine.sha256(source)
    job = tmp_path / "job"
    job.with_suffix(".cancel").touch()
    report = engine.run_job(source, ["freeccr"], dict(encoding="linear", grade=3.3, exposure=1.06), job)
    assert report["status"] == "cancelled"
    assert digest == engine.sha256(source)
    assert not (job / "freeccr.tif").exists()
    assert not job.with_suffix(".cancel").exists()


def test_existing_job_is_never_overwritten(tmp_path):
    job = tmp_path / "job"
    job.mkdir()
    sentinel = job / "keep.txt"
    sentinel.write_text("keep")
    with pytest.raises(FileExistsError):
        engine.run_job(tmp_path / "missing.tif", [], {}, job)
    assert sentinel.read_text() == "keep"


def test_repeated_conversions_share_one_flat_folder(tmp_path):
    source = tmp_path / "源 scan.tif"
    tifffile.imwrite(source, negative(), photometric="rgb", resolution=(4800, 4800), resolutionunit="INCH")
    source_hash = engine.sha256(source)
    output_dir = tmp_path / "converted"
    options = dict(encoding="linear", grade=3.3, exposure=1.06)
    first = engine.run_job(source, ["freeccr"], options, tmp_path / "jobs" / "first", output_dir)
    first_path = Path(first["results"]["freeccr"]["path"])
    first_hash = engine.sha256(first_path)
    second = engine.run_job(source, ["freeccr"], options, tmp_path / "jobs" / "second", output_dir)
    second_path = Path(second["results"]["freeccr"]["path"])
    assert first["status"] == second["status"] == "complete"
    assert first_path == output_dir / "源 scan_freeccr.tif"
    assert second_path == output_dir / "源 scan_freeccr_2.tif"
    assert engine.sha256(first_path) == first_hash == engine.sha256(second_path)
    assert engine.sha256(source) == source_hash
    assert len(list(output_dir.iterdir())) == 4
    assert all(path.is_file() for path in output_dir.iterdir())
    for report in (first, second):
        result = report["results"]["freeccr"]
        assert result["info"]["path"] == result["path"]
        assert Path(result["preview"]).parent == output_dir
        assert report["results_dir"] == str(output_dir)


@pytest.mark.parametrize("extension", ["tif", "jpg"])
def test_shared_output_preserves_existing_tiff_or_preview(tmp_path, extension):
    output_dir = tmp_path / "converted"
    output_dir.mkdir()
    existing = output_dir / f"scan_negadoctor.{extension}"
    existing.write_bytes(b"earlier result")
    master = tmp_path / "master.tif"
    preview = tmp_path / "preview.jpg"
    master.write_bytes(b"TIFF fixture")
    preview.write_bytes(b"JPEG fixture")
    first, first_preview = engine.publish_result(master, preview, tmp_path / "a" / "scan.tif",
                                                 "negadoctor", output_dir)
    second, second_preview = engine.publish_result(master, preview, tmp_path / "b" / "scan.jpg",
                                                   "negadoctor", output_dir)
    assert first.name == "scan_negadoctor_2.tif" and second.name == "scan_negadoctor_3.tif"
    assert first.read_bytes() == second.read_bytes() == master.read_bytes()
    assert first_preview.read_bytes() == second_preview.read_bytes() == preview.read_bytes()
    assert existing.read_bytes() == b"earlier result"
    assert len(list(output_dir.iterdir())) == 5


def test_publication_failure_keeps_working_files_and_removes_incomplete_pair(monkeypatch, tmp_path):
    output_dir = tmp_path / "converted"
    master = tmp_path / "master.tif"
    preview = tmp_path / "preview.jpg"
    master.write_bytes(b"TIFF fixture")
    preview.write_bytes(b"JPEG fixture")

    def fail_copy(source, destination, **kwargs):
        destination.write(b"incomplete")
        raise OSError("disk full")

    monkeypatch.setattr(engine.shutil, "copyfileobj", fail_copy)
    with pytest.raises(OSError, match="disk full"):
        engine.publish_result(master, preview, tmp_path / "scan.tif", "freeccr", output_dir)
    assert not list(output_dir.iterdir())
    assert master.read_bytes() == b"TIFF fixture" and preview.read_bytes() == b"JPEG fixture"


def test_completed_result_survives_another_engine_failure(tmp_path):
    source = tmp_path / "scan.tif"
    tifffile.imwrite(source, negative(), photometric="rgb")
    output_dir = tmp_path / "converted"
    report = engine.run_job(source, ["freeccr", "missing-engine"], {}, tmp_path / "job", output_dir)
    assert report["status"] == "partial" and report["original_preserved"]
    assert "Unknown converter" in report["errors"]["missing-engine"]
    assert Path(report["results"]["freeccr"]["path"]).is_file()
    assert Path(report["results"]["freeccr"]["preview"]).is_file()


def test_default_jobs_are_internal_and_outputs_are_shared():
    assert engine.new_job_path().parent == engine.HERE / "local-data" / "jobs"
    assert engine.RESULTS == engine.HERE / "Results"


def test_dpi_update_preserves_compressed_pixel_payload(tmp_path):
    path = tmp_path / "output.tif"
    tifffile.imwrite(path, negative(), photometric="rgb", compression="deflate", resolution=(300, 300))
    with tifffile.TiffFile(path) as tf:
        page = tf.pages[0]
        segments = list(zip(page.dataoffsets, page.databytecounts))
    original = path.read_bytes()
    engine.preserve_dpi(path, [4800, 9600])
    changed = path.read_bytes()
    assert all(original[offset:offset + count] == changed[offset:offset + count] for offset, count in segments)
    assert engine.inspect_image(path)["dpi"] == [4800, 9600]
    np.testing.assert_array_equal(tifffile.imread(path), negative())
