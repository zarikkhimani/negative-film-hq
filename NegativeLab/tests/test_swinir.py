import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import ImageCms
import pytest
import tifffile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import engine


@pytest.mark.parametrize("options", [{"swinir_device": "automatic"}, {"swinir_tile": 0},
                                    {"swinir_tile": 63}, {"swinir_tile": 129}])
def test_invalid_swinir_options_fail_clearly(options):
    with pytest.raises(ValueError, match="SwinIR"):
        engine.validate_swinir_options(options)


@pytest.fixture
def positive(tmp_path):
    pixels = np.arange(65 * 81 * 3, dtype=np.uint16).reshape(65, 81, 3) * 3
    icc = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    source = tmp_path / "正片 positive.tif"
    tifffile.imwrite(source, pixels, photometric="rgb", compression="deflate", iccprofile=icc,
                     resolution=(4800, 4800), resolutionunit="INCH")
    return source, pixels, icc


def fake_install(monkeypatch, tmp_path):
    installation = tmp_path / "SwinIR"
    model = installation / "model.pth"
    for path in (installation / ".venv" / "Scripts" / "python.exe", installation / "upscale_x2.py", model):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"test fixture")
    monkeypatch.setattr(engine, "SWINIR", installation)
    monkeypatch.setattr(engine, "SWINIR_MODEL", model)
    return installation


def test_upscale_adapter_preserves_profile_precision_and_source(monkeypatch, tmp_path, positive):
    fake_install(monkeypatch, tmp_path)
    source, pixels, icc = positive
    original_hash = engine.sha256(source)
    commands = []

    def spawn(command, **kwargs):
        commands.append(command)
        supplied = Path(command[3])
        target = Path(command[command.index("--output") + 1]) / f"{supplied.stem}_SwinIR_x2.tif"
        # This process boundary fixture stands in for inference; the real GPU is tested separately.
        result = np.repeat(np.repeat(tifffile.imread(supplied), 2, axis=0), 2, axis=1)
        tifffile.imwrite(target, result, photometric="rgb", compression="lzw")
        return SimpleNamespace(returncode=0, poll=lambda: 0)

    monkeypatch.setattr(engine.subprocess, "Popen", spawn)
    report = engine.run_job(source, ["swinir"], {"swinir_device": "cuda", "swinir_tile": 128},
                            tmp_path / "job", tmp_path / "converted")
    assert report["status"] == "complete"
    assert report["input_kind"] == "positive" and "negative" not in report
    assert report["original_preserved"] and engine.sha256(source) == original_hash
    output = Path(report["results"]["swinir"]["path"])
    assert output.parent == tmp_path / "converted"
    with tifffile.TiffFile(output) as tf:
        assert tf.pages[0].tags[34675].value == icc
        assert tf.pages[0].bitspersample == 16
    np.testing.assert_array_equal(tifffile.imread(output), np.repeat(np.repeat(pixels, 2, axis=0), 2, axis=1))
    assert engine.inspect_image(output)["dpi"] == [4800, 4800]
    assert len(commands) == 1 and commands[0][commands[0].index("--device") + 1] == "cuda"
    assert not (tmp_path / "job" / "swinir-decode.tmp").exists()
    assert not list((tmp_path / "job" / "swinir-work").glob("*.tif"))


def test_swinir_failure_has_no_cpu_fallback(monkeypatch, tmp_path, positive):
    fake_install(monkeypatch, tmp_path)
    source, _, _ = positive
    commands = []

    def spawn(command, **kwargs):
        commands.append(command)
        kwargs["stdout"].write("ERROR: CUDA out of memory\n")
        kwargs["stdout"].flush()
        return SimpleNamespace(returncode=1, poll=lambda: 1)

    monkeypatch.setattr(engine.subprocess, "Popen", spawn)
    report = engine.run_job(source, ["swinir"], {}, tmp_path / "failed-job")
    assert report["status"] == "failed" and "CUDA out of memory" in report["errors"]["swinir"]
    assert report["original_preserved"] and not report["results"]
    assert len(commands) == 1


def test_missing_swinir_component_is_reported(monkeypatch, tmp_path, positive):
    monkeypatch.setattr(engine, "SWINIR", tmp_path / "missing-installation")
    job = tmp_path / "missing-job"
    job.mkdir()
    with pytest.raises(FileNotFoundError, match="SwinIR component is missing"):
        engine.run_swinir(positive[0], job, engine.inspect_image(positive[0]), {})
