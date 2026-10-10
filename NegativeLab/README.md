# NegativeLab

A local Windows interface for the FreeCCR, darktable and SwinIR installations in this photography workspace.

Double-click **Start NegativeLab.cmd** in the parent folder. You can also drag one negative onto that launcher.

1. Leave the source selector on **Negative scan**. Drag one **unconverted TIFF or JPEG negative** into the viewer, or click **Choose image…**.
2. Select **FreeCCR**, **darktable / Negadoctor**, or **Both — compare results**.
3. Click **Convert negative**. Results appear as they finish; **Compare** shows both positives beside each other.
4. Use **Open results folder** for the full-resolution TIFFs. **Finish result in darktable** opens the selected positive for further editing.
5. Optionally select a positive result and click **Upscale selected result 2×**. The enlargement appears in **SwinIR 2×** and is saved alongside the conversions in the same results folder.

Negadoctor is darktable's negative-conversion module, so the interface has two conversion engines. Both processes the same negative independently, running FreeCCR first and darktable second. To use them in sequence, convert with FreeCCR and then finish that positive in darktable.

## Optional SwinIR upscaling

**SwinIR never runs automatically during negative conversion.** Select the FreeCCR or Negadoctor tab, or choose a result in Compare, then click **Upscale selected result 2×** when you want it. Both converted masters remain available and unchanged. The SwinIR tab shows the latest enlargement; previous runs remain saved in the shared results folder.

To upscale an existing positive TIFF or JPEG, choose **Positive photo — SwinIR** in the source selector, load the image, then click **Upscale positive 2×**. Loading an image does not start processing. Convert a negative to a positive before using SwinIR.

This uses the installed **SwinIR Classical SR x2** checkpoint. It doubles width and height and saves a losslessly compressed 16-bit RGB TIFF, preserving the input ICC profile and DPI when present. It runs super-resolution; it does not convert negatives, perform dust removal or recover missing source detail with certainty. Review fine textures and film grain before using the enlargement as a final image.

Under **SwinIR settings**, the default is **NVIDIA GPU**, tile size **256**. You can explicitly select CPU or a smaller tile. Smaller tiles reduce inference memory, but large images still need memory for the full output. A GPU error is reported with a log path; the app does not silently switch to CPU or another method. **Cancel processing** stops a running upscale.

## Conversion and editing

- **FreeCCR:** uses the installed `core.ccr_processor` reference-normalization and optical-density alignment functions, including their standard positive look. Reference statistics come from a 1080-pixel-or-smaller sample with a 2% inset. The entire image is exported; there is no automatic frame crop or fine rotation. FreeCCR's roll-wide B/W anchors, stock presets, dust cleanup and other adjustments remain available through **Open negative in FreeCCR**.
- **darktable / Negadoctor:** creates editable starting settings and exports using the installed `darktable-cli.exe`. Tone-mapping modules are omitted from the supplied history. The explicit working profile is linear Rec.709, matching the input assumptions used by the existing workspace sample. These automatic settings are an estimate, not a calibrated film/scanner profile.
- **Edit negative in darktable:** prepares a separate working copy with Negadoctor enabled. The editable negative and its `.xmp` are kept together. If the last run used only FreeCCR, this button prepares a new editing job.
- **Finish result in darktable:** opens a positive TIFF without enabling Negadoctor on it. In Compare, choose which result to finish using the result selector.

Under **Negadoctor settings**, choose **Linear scanner RGB** for an assumed linear scan, or **sRGB-encoded scan / JPEG** for that encoding. JPEG defaults to sRGB; TIFF defaults to linear. The wrapper explicitly overrides embedded scanner ICC interpretation for Negadoctor, so choose an encoding appropriate to the scan. Other scanner profiles and camera RAW workflows should be handled in the full editors.

Use **Sample clear film base**, then click a clean, unexposed film patch beside the photograph. The picker takes the median of a 7 × 7 patch in the bounded preview. Without a sample, base values are estimated from channel percentiles. Paper grade and print exposure can be adjusted before another run. Color balance and density estimates still need visual review, especially on cropped frames without clear film base. Include one complete frame with as little holder area as practical.

The official [Negadoctor manual](https://docs.darktable.org/usermanual/5.6/en/module-reference/processing-modules/negadoctor/) explains film-base sampling and the module controls. Export uses the documented [darktable CLI](https://docs.darktable.org/usermanual/5.6/en/special-topics/program-invocation/darktable-cli/) with the generated XMP sidecar.

## Files and precision

All converted images and enlargements are saved directly in **`NegativeLab/Results/`**, with no per-run output folders:

- `<source>_freeccr.tif`, `<source>_negadoctor.tif`: full-resolution, losslessly compressed 16-bit RGB positives with sRGB ICC profiles.
- `<source>_swinir-x2.tif`: optional enlargement, preserving the selected positive's profile and DPI. Upscaling a conversion keeps its converter name, such as `scan_freeccr_swinir-x2.tif`.
- Matching `.jpg` previews beside each TIFF.

Repeated runs and source images with matching names get numbered suffixes (`_2`, `_3`, etc.). Neither an existing TIFF nor its JPEG preview is overwritten. **Open results folder** always opens this shared folder.

Protected working files and diagnostics are kept separately under `NegativeLab/local-data/jobs/<timestamp>_<id>/`:

- `source.tif` / `source.jpg`: byte-identical snapshot, including any ancillary infrared pages.
- `negative.tif`: lossless 16-bit RGB working copy with orientation baked into its pixels.
- `positive.tif`: corresponding protected working copy for a standalone SwinIR job.
- `negative.tif.xmp`: editable Negadoctor settings when that workflow is used.
- `job.json` with parameters/source hash and the shared output paths, plus diagnostic logs and isolated editor/runtime state.

Original files and original sidecars are never edited. Completed jobs verify the original SHA-256 against the captured snapshot. Cancelled/failed jobs retain useful completed files and diagnostics; temporary partial TIFF exports are removed. Completed output from one engine remains usable if the other fails, and the interface reports that failure. Files from earlier versions remain in their original folders.

Unsigned 8- and 16-bit RGB TIFFs, including stripped, tiled and planar layouts, and RGB JPEGs are supported. Reduced thumbnail and infrared/mask pages may accompany the primary RGB page; these remain in the source snapshot but are not converted or used for dust removal. Multiple full photographic pages, grayscale/CMYK images, alpha channels, floating-point TIFFs and RAW files are rejected clearly. One image is processed at a time. 8-bit sources can be exported to 16-bit containers, but gain no source precision. Working copies and TIFF results preserve scanner DPI, including swapped axes for rotated orientations. The wrapper restores darktable's resolution tags to source DPI without re-encoding its pixels.

Preview reading keeps a bounded sampled image. FreeCCR conversion uses disk-backed decoding and processes output in strips, preserving full resolution while limiting intermediate arrays. Large scans need several times their decoded RGB size in free disk space. No new scanner acquisition is involved.

## Runtime

This app reuses `FreeCCR/.venv` (PySide6, NumPy, OpenCV, Pillow, tifffile, imagecodecs and ONNX Runtime). SwinIR runs separately through `SwinIR/.venv/Scripts/python.exe` and the existing `SwinIR/upscale_x2.py`; its PyTorch dependencies stay in that environment. The required checkpoint is `SwinIR/model_zoo/swinir/001_classicalSR_DF2K_s64w8_SwinIR-M_x2.pth`. Missing components produce a clear error. No new system install, global package, PATH or registry setting is required. Keep `NegativeLab`, `FreeCCR`, `darktable`, `SwinIR`, and the launcher together.

Background jobs use isolated config/catalog folders. Compiled darktable kernels are reused under `NegativeLab/local-data` to avoid rebuilding them on every run. Manual darktable editing uses a job-specific catalog, separate from the usual darktable launcher. FreeCCR's full editor continues to use its existing local settings/catalog. The wrapper logs parameters and uses actual conversion errors; it does not substitute another engine when one fails.

The bundled XMP template uses darktable 5.6.1 colorin version 7 and Negadoctor version 2 parameter layouts, checked against the workspace's saved upstream source. Revalidate this adapter before replacing darktable with another version. FreeCCR code remains in its existing AGPL-3.0 project and is imported from there; this companion does not change that source. Its reference conversion runs on the CPU; darktable uses the installed OpenCL configuration.

## Validation

From the photography folder:

```powershell
.\NegativeLab\test.ps1
```

This runs file/precision tests and an offscreen Qt smoke test with actual converter subprocesses. It exercises shared output naming and conflict protection, drag/drop, all three modes, original preservation, the film-base picker, immediate and in-progress darktable cancellation, and editor preparation/launch arguments. Rendered JPEGs and reports are stored under `NegativeLab/test-output`. The smoke test does not open the actual editor windows.

Include the real SwinIR GPU smoke test with:

```powershell
.\NegativeLab\test.ps1 -SwinIR
```

The SwinIR test exercises manual upscaling from both converter results and an existing positive JPEG, unchanged source/master hashes, doubled dimensions, 16-bit output, byte-identical ICC profiles, preserved DPI, and cancellation during GPU inference. Its report is `test-output/swinir-gui/report.json`.

Full-resolution conversion of the existing 3372 × 4932, 16-bit Signynt sample succeeded with both engines; `test-output/full-sample-v3/job.json` records outputs and matching source hash. Its darktable log confirms Negadoctor executed on the RTX 4080 Laptop GPU. The automatically estimated positive is a starting point; the earlier hand-tuned sample remains separate.

The existing 5184 × 1200, 48-bit Canon scan also completed through both engines. `test-output/real-canon48-final/job.json` records the results, preservation of 4800 DPI and unchanged original hash. No new physical scan was performed.

Optional command-line use:

```powershell
.\FreeCCR\.venv\Scripts\python.exe .\NegativeLab\engine.py .\Samples\Signynt\Example.tif --engine both
```

To upscale a positive directly:

```powershell
.\FreeCCR\.venv\Scripts\python.exe .\NegativeLab\engine.py .\positive.tif --engine swinir --swinir-device cuda --swinir-tile 256
```

Both commands use the shared results folder. Pass `--output <folder>` to use another shared destination; `--job` only controls the internal working folder.
