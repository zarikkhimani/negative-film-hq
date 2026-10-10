# SwinIR Classical SR x2 (Windows)

This checkout uses JingyunLiang/SwinIR and exactly:
`001_classicalSR_DF2K_s64w8_SwinIR-M_x2.pth`.
The model architecture is Classical SR, scale 2, training patch size 64,
window size 8. The training patch size is a model setting, not a crop size.

## Everyday use

Double-click `Start SwinIR x2.cmd` in the parent photography folder and select
one or more photos. You can also drag image files or a folder onto that launcher.
The console reports progress and stays open when processing finishes.

Results are saved to `SwinIR/output/` as `<name>_SwinIR_x2.tif` by default.
TIFF uses lossless LZW compression. PNG remains available with `--format png`.
Width and height each double. Existing files are never overwritten; repeated
runs receive numbered output names. Folder input processes images directly in
that folder, without recursing into subfolders.

Supports 8-bit and 16-bit RGB/grayscale PNG, JPEG, TIFF, BMP, and WebP as decoded
by OpenCV. Outputs are RGB TIFF or PNG at the input bit depth. Raw camera files, alpha
channels, floating-point images, and multipage TIFF workflows are not supported.
Image metadata and ICC profiles are not carried into the output; export photos
to an appropriate RGB color space before using this tool. Supply images already
oriented correctly.

The default uses the NVIDIA GPU and 256-pixel tiles with 32-pixel overlap to
limit memory use. Tile processing can differ slightly from whole-image inference.
GPU errors stop with an error message. CPU execution must be requested explicitly.

## Command line (PowerShell, from this folder)

```powershell
.\.venv\Scripts\python.exe upscale_x2.py "C:\path\photo.jpg"
.\.venv\Scripts\python.exe upscale_x2.py "C:\path\photos" --output "C:\path\enlarged"
# Use PNG instead of the default TIFF:
.\.venv\Scripts\python.exe upscale_x2.py "C:\path\photo.tif" --format png
# Smaller tiles use less GPU memory:
.\.venv\Scripts\python.exe upscale_x2.py "C:\path\photo.tif" --tile 128
# Whole-image inference, for small images:
.\.venv\Scripts\python.exe upscale_x2.py "C:\path\photo.png" --tile 0
# Explicit CPU mode (slower):
.\.venv\Scripts\python.exe upscale_x2.py "C:\path\photo.jpg" --device cpu
```

This is the Classical SR checkpoint trained for bicubic degradation, as requested.
It is not a denoising or film-negative conversion step.

## Environment and reproducibility

Python 3.12 is isolated in `.venv`, created from Codex's bundled Python runtime.
If that base runtime is removed or moved, recreate the venv using Python 3.12.
No global Python packages or system settings are changed.

```powershell
# Recreate .venv first with an available Python 3.12 interpreter, if necessary.
.\.venv\Scripts\python.exe -m pip install torch==2.7.1 torchvision==0.22.1 --index-url https://download.pytorch.org/whl/cu128 --cache-dir .pip-cache
.\.venv\Scripts\python.exe -m pip install -r requirements-local.txt --cache-dir .pip-cache
.\.venv\Scripts\python.exe download_model.py
.\.venv\Scripts\python.exe -m pip check
```

The downloader uses the exact official GitHub release URL, checks download
length when supplied, and prints the local SHA256. The hash records the bytes
downloaded; it is not an independently published upstream checksum.
`requirements-lock.txt` records all installed Python package versions.

The local runner reuses upstream model loading and tile inference. The only
change to upstream code loads the checkpoint on CPU with `weights_only=True`,
before transferring the model to the requested device.

## Official benchmark

```powershell
.\.venv\Scripts\python.exe -u main_test_swinir.py --task classical_sr --scale 2 --training_patch_size 64 --model_path model_zoo/swinir/001_classicalSR_DF2K_s64w8_SwinIR-M_x2.pth --folder_lq testsets/Set5/LR_bicubic/X2 --folder_gt testsets/Set5/HR
```

Benchmark images are saved under `results/swinir_classical_sr_x2/`.

Sources: [official repository](https://github.com/JingyunLiang/SwinIR),
[checkpoint release](https://github.com/JingyunLiang/SwinIR/releases/tag/v0.0),
[PyTorch wheel instructions](https://pytorch.org/get-started/previous-versions/).
