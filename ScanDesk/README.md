# FilmDesk: a 35mm film scanning prototype

FilmDesk is a local Windows app for the Canon MG8100 series. It hosts the installed Canon ScanGear TWAIN interface, receives 48-bit film frames, and saves each frame automatically as a lossless TIFF. It displays the saved filename, location and metadata without decoding or displaying an image preview. Rotation remains available and preserves originals. It uses the installed 32-bit Canon driver, Windows .NET Framework and the bundled project-local LibTiff.NET library; no system installation is needed.

The workflow is **Scan → automatically saved TIFF**, with no format choice or second save/export step. Scan saves and rotated copies use TIFF with lossless LZW compression, preserving the pixels received from Canon. PNG output is disabled; importing older PNG/BMP scans converts them to TIFF in the new session. Existing TIFF/JPEG files can also be imported.

## Start

Double-click `bin\FilmDesk.exe`. Keep the executable inside this project folder: it stores scans in `Scans\<session>` relative to the project. Every received frame is saved immediately. Closing the app does not delete scans; use **Import / recover images** to reopen an earlier session. Removed frames and originals before rotation remain on disk.

1. Close MP Navigator or other scanning apps that might occupy the scanner.
2. Remove the film adapter protective sheet from the lid and load the Canon 35mm film guide as described in the Canon manual. The strip guide supports up to six frames. Mounted slides use the slide configuration of that guide.
3. Select **Canon MG8100 ser** for the USB connection. The source with a suffix is the separately installed network source. FilmDesk excludes WIA sources because the MG8100 WIA driver cannot scan film.
4. Click **Open ScanGear for film**. FilmDesk sets the TWAIN light path to transmissive and stops if the driver rejects it.
5. Before **Preview** or **Scan**, open **Preferences → Scanner** and enable **Quiet Mode**. Leave scan music and completion sounds disabled if you want a silent workspace.
6. Choose **4800 dpi (optical)** or **9600 dpi** in FilmDesk's **Film preset** selector. In **Advanced Mode**, select **Color Positive Film**, **35mm Strip**, **Color(48bit)**, the same DPI as the selected preset, **Flexible**, and **100%**. The positive-film source preserves the orange negative for later inversion. Negative Film deliberately enables Canon's inversion.
7. Use **Whole Film Image** view and manual crops. Use Canon's manual Preview if needed to position regions, then check **Manual Exposure at 100%**. Long strips need overlapping regions within the limits below. Check Quiet Mode and all corrections are disabled, then Scan. Close ScanGear after transfer.
8. FilmDesk confirms the saved filename, location and metadata. Use **Open scan folder** to access the TIFF; no image preview, export or second save step is needed. Canon's **Preview at Start of ScanGear** is set to **None** on this computer. Manual Preview remains available in Canon for positioning film regions; scanning without that setup preview has not been physically verified.

## Quiet mode requirement and current limitation

The intended operating preference is **quiet mode for every preview and scan**. The installed MG8100 manual documents a Quiet Mode checkbox in ScanGear's Scanner preferences; enabling it slows the scanner head. FilmDesk displays this requirement prominently.

This prototype does **not** programmatically set or verify that driver checkbox. TWAIN has no standard quiet-mode capability, and the installed Canon driver reports its custom driver-settings capability as unsupported. Until a supported way to control or verify it is established, check the ScanGear checkbox before each preview or scan. FilmDesk makes no claim that quiet mode is enforced automatically or that film calibration is silent.

## 4800 and 9600 dpi / 48-bit film presets

Canon's MG8120 specification lists **4800 × 9600 dpi optical film resolution** and **48-bit film output**. Therefore **4800 × 4800 dpi at 100%** stays within the optical limits on both axes and remains the default. The optional **9600 × 9600 dpi** preset exceeds the horizontal optical sampling limit; it is labeled accordingly in the app. Both use the same positive-film source, 48-bit RGB, 100% Flexible output and disabled corrections. The app never resamples: it requires the received X/Y DPI to match the selected preset and rejects mismatches before saving. 19200 dpi remains unsupported. See [Canon's specifications, printed page 51](https://gdlp01.c-wss.com/gds/8/0300003908/01/MG8120_GS_EN-US_V1.pdf).

In **Preferences → Scan**, enable **48/16 bit Output**, then select **Color(48bit)** in Advanced Mode. **Preset settings** in FilmDesk provides the checklist for the selected resolution. The named Canon favorite **FilmDesk 4800 - orange negative** is saved on this computer. For 9600 dpi, apply the same settings and change Output Resolution to **9600**, with a smaller manual region. You can save a separate favorite as **FilmDesk 9600 - orange negative** using **Favorite Settings → Add/Delete** after Preview; FilmDesk's preset selector does not itself create Canon favorites. Canon owns the film subtype, correction switches, scale, crop and Quiet Mode. FilmDesk requests transmissive film, RGB, 16 bits/channel and the selected DPI through TWAIN; it validates actual received bit depth, channel layout and X/Y DPI before saving. Successful standard capability requests alone do not prove that Canon applied them. The preset selector is locked while ScanGear is open.

In Advanced Mode, choose **35mm Strip** explicitly for Scan Area and use the toolbar's **Whole Film Image** view. Preview, then use manually drawn rectangles without automatic frame detection. Unlock the input aspect ratio when changing the rectangle. The full window in this driver is approximately 1.22 × 9.50 inches. Canon's installed manual (`Sg-804.html`) documents a maximum scan size of 21000 × 30000 pixels and 1.8 GB. At 4800 dpi, 30000 pixels corresponds to 6.25 inches; the full 9.50-inch window would be about 45600 pixels tall. A long strip may therefore require two overlapping manual regions, each no taller than 6.25 inches, at Flexible output size and 100% scale. This keeps the requested resolution without enlargement, frame detection or downsampling. Whole-window acquisition at 4800 dpi remains unverified; the earlier whole-window scan was at 2400 dpi.

At **9600 dpi**, 30000 pixels is **3.125 inches**, but the **1.8 GB** limit is tighter for the approximately 1.22-inch-wide film window in 48-bit RGB. Use overlapping regions up to **2.5 inches tall at that width** (about 1.69 GB of samples), or smaller regions as needed. This may require more than two regions for a long strip. These are scan regions at 100% scale; FilmDesk does not detect frames, stitch regions or reduce resolution. A physical 9600 dpi acquisition has not yet been verified.

Set Preferences → Color Settings to **None** and Preferences → Preview → Cropping Frame on Previewed Images to **None**. Set Image Adjustment/auto tone/auto color to **None/OFF**, Unsharp Mask/sharpening to **OFF**, dust/scratch reduction, fading, grain and backlight correction to **None/OFF**, Descreen to **OFF**, and High Quality to **OFF**. Some controls are absent for the positive-film source. Use no custom tone curve. After each preview, enable **Manual Exposure at 100%** to disable the driver's automatic crop exposure; it resets when ScanGear reopens. Keep Quiet Mode enabled. Hardware calibration remains enabled. This preserves the driver-delivered 16-bit samples; it does not claim hardware RAW or bypass Canon's analog processing.

48-bit frames use TWAIN buffered memory transfer directly into lossless LZW TIFF, preserving RGB sample values and DPI. There is no BMP, JPEG or PNG intermediate in this path. A temporary TIFF is published only after every row arrives and the TIFF directory is finalized; failures and cancellation never publish incomplete scans. FilmDesk does not generate or display an image preview after scanning, importing or rotating; it reads only file metadata for the saved-file confirmation. The saved scan remains full resolution and 16 bits/channel. Rotation copies the TIFF and updates orientation metadata without re-encoding samples; the original remains untouched. The older native DIB and bounded-preview helpers remain for recovery tests, not current acquisition or display.

## Current scope

### Experimental control without the Canon setup window

An isolated test executable can request scan coordinates through `DAT_IMAGELAYOUT` and enable the driver with `ShowUI=FALSE`. Build it with `.\build.ps1 -Experimental`; the existing `bin\FilmDesk.exe` is not replaced. `bin\FilmDesk.HeadlessTest.exe --headless-probe` requests and checks a 0.90 x 0.25 inch rectangle at platen coordinates (3.45, 1.35) through (4.35, 1.60) inches, within Canon's reported default film frame, without requesting a scan or preview. Close ScanGear and other scanner software first. These are physical platen coordinates, not offsets within the approximately 1.22 x 9.50 inch film window.

For an explicitly requested physical test, first inspect Quiet Mode, positive film, 48-bit output and disabled corrections in ScanGear, then close ScanGear. `bin\FilmDesk.HeadlessTest.exe --headless-scan --quiet-verified` starts the experimental acquisition. The flag records an operator check; it does not automatically verify Quiet Mode. Actual bit depth, DPI and crop dimensions are checked before TIFF publication. The test does not display an image or silently substitute the normal Canon interface. Reports are saved under `test-output\headless-probe.txt` and `headless-scan.txt`.

The experimental build passed the existing self-tests, including the new TWAIN frame/layout ABI and fractional-coordinate checks. The first connection-only probe stalled while the original ScanGear settings window remained open, and its process was stopped. After Preferences, ScanGear and FilmDesk were closed, the connection-only probe completed successfully and Canon accepted the supplied rectangle with exact coordinate readback. A subsequent physical hidden-window acquisition stalled at EnableDS without returning image data; the test helper was stopped after approximately five minutes and no TIFF was created. See `test-output\headless-test-status.md`. Hidden acquisition has not succeeded. Full custom frame selection and reliable control of Canon's private correction and Quiet Mode settings remain unimplemented.

- 35mm film through Canon ScanGear, with film type, resolution, frame detection and corrections controlled in the driver UI.
- Selectable 4800 or 9600 dpi, 48-bit RGB acquisition. Each preset rejects 24-bit color, mismatched X/Y DPI, compressed/planar TWAIN samples and incomplete or incorrectly ordered transfer chunks. Single-page stripped unsigned RGB 48-bit TIFF imports are supported. 16-bit grayscale, tiled high-depth and multipage TIFF imports are unsupported and rejected clearly.
- No PDF/document workflow, OCR, cloud upload, automatic shutter/film advance, or custom negative inversion pipeline.
- Scanned TIFFs remain local under unique names. Completed scans are saved automatically; a temporary file protects against partial writes.

## Verification performed

A physical scan of approximately the bottom third of the film window succeeded on October 2, 2026, with the 4800 dpi preset, positive film, true 48-bit RGB, 100% output/manual exposure, available corrections disabled and Quiet Mode checked. FilmDesk automatically saved `Scans\2026-10-02_202624_425bb5\frame-203530-0526d761.tif` (5806 x 15161 pixels, 549,121,108 bytes) without displaying an image preview. Independent decoding of the entire TIFF confirmed exactly 4800 dpi on both axes, genuine 16-bit samples and lossless LZW. One manual region was scanned; the physical frame count remains unverified. See `test-output\one-third-4800-scan.md`.

Both resolution presets passed the build and TIFF precision tests. The connected Canon driver accepted 9600 dpi requests on both axes and reported 9600 dpi in capability readbacks. The app's selector and preset summary were exercised at 9600 dpi; ScanGear opened with positive film, Color(48bit) and the available corrections OFF/None, but retained 4800 dpi in its screen. Setting that field manually to 9600 dpi was accepted. No preview or physical 9600 dpi scan was requested. Independent tifffile/imagecodecs decoding confirmed every sample in both synthetic TIFF fixtures and their exact X/Y DPI.

The scan-and-save interface passed the existing build, image/UI tests and connected-scanner probe. Recovering the physical 48-bit test TIFF through the running app displayed its saved filename, location, 5184 x 1200 dimensions, 4800 dpi and 48-bit depth without an image preview. The recovered TIFF was verified byte-for-byte identical to the original. No new physical scan was requested for this display-only change.

`test-output\self-test.txt` records checks for both 4800 and 9600 dpi presets: exact low/high-byte preservation in 48-bit TIFF, actual X/Y DPI metadata, padded multi-chunk transfer, four lossless rotations, bounded preview helpers, import/copy and rejection of incorrect depth/DPI, truncated/out-of-order/incomplete transfers and lossy 48-bit saving. It also verifies the 32-bit TWAIN structures. Existing DIB, 24-bit encoding, original preservation, atomic-write recovery and rendered UI checks are retained. The legacy 3000 × 23000 native-buffer test remains as a regression check.

`test-output\scanner-probe.txt` records a connection to **Canon MG8100 ser**, verified buffered memory transfer and transmissive film light path, plus accepted requests and exact readbacks for 4800/9600 dpi and 16-bit channel requests. Canon can accept a 16-bit request while reporting 8-bit current depth before its screen opens. Its UI also retained the previous 4800 dpi setting when opened after a successful 9600 dpi request. **Check and set Output Resolution in ScanGear to match FilmDesk before scanning.** Actual transfer metadata is authoritative; mismatches are rejected rather than downsampled or mislabeled. This probe does not request a preview or scan. `test-output\verify-48bit.py` independently decodes both DPI fixtures using tifffile/imagecodecs and confirms every 16-bit value and both resolution tags.

**A physical 4800 dpi / 48-bit positive-film test succeeded on October 2, 2026.** Its original TIFF is `Scans\2026-10-02_194404_5ddcd8\frame-195721-d128cbb6.tif`: 5184 × 1200 pixels, unsigned 16-bit RGB, exactly 4800 dpi on both axes, lossless LZW. An independent decoder confirmed the metadata and low-bit variation; FilmDesk displayed the orange negative. Quiet Mode was checked, Color Settings was None, the available corrections were disabled, and Manual Exposure/output scale were 100%. This was a small manually positioned test region, not a complete frame or strip. The 5872 × 30000 synthetic 48-bit stress test also passed, processing 1.06 GB of pixels with a 34 MiB peak working set. See `test-output\real-48bit-scan-test.md`.

**A real 35mm preview and single-frame scan succeeded on October 2, 2026.** ScanGear detected three frames; frame 3 was scanned using Color Negative Film, Color, Flexible output size at 100%, and 2400 DPI. FilmDesk received the image, saved it automatically, and displayed it. The saved PNG decodes at 3312 × 2272 pixels with approximately 2400 DPI metadata. Quiet Mode was visibly checked before preview and scan, and both sound options were disabled. Acoustic noise was not independently measured.

The original scan is `Scans\2026-10-02_180730_58ebba\frame-181214-b8a6e6d2.png`. Rotation was tested through the app while preserving that original, and an upright copy was exported through the app as `film-test-upright.tif` in the same folder. The scanned area includes a black edge that has not been cropped. Multi-frame transfer in one batch remains untested. The current rendered app preview is `test-output\app-preview.tif`.

A full-window scan with corrections disabled also succeeded at 2400 DPI after fixing excess memory use during native transfer. Its lossless PNG is `Scans\2026-10-02_184915_d72bd6\frame-185937-aa6d520a.png` (2936 × 22840 pixels, approximately 98 MB). Quiet Mode was checked before preview and scan. Only one recognizable photograph is visible in the full-area image; capture of all six user-reported physical frames remains unverified. See `test-output\real-scan-test.md` for settings, the original failed attempt, and the successful retry.

After the user specified TIFF/JPEG only, that full scan and the cropped negative were converted to `.tif` alongside the old originals. Both TIFFs were independently decoded and verified to have identical RGB pixels, dimensions, and DPI. The cropped negative is also available as `first-negative-cropped.jpg` at quality 95. The revised TIFF-default binary passed all tests and the scanner probe; no new physical scan was needed for this format change.

## Build and test

From PowerShell in this project:

```powershell
.\build.ps1
.\test.ps1
```

The build uses Windows' existing .NET Framework C# compiler and targets x86 for Canon's installed TWAIN driver. `test.ps1` rebuilds, runs image/UI tests, then probes the connected Canon scanner without acquiring images. Diagnostic failures produce a nonzero exit code and a report.

The pinned TIFF dependency is **BitMiracle.LibTiff.NET 2.4.660**, bundled under `vendor\libtiff` and copied beside the executable. The NuGet archive SHA-256 is `2779C539262F5C68B37EB19D62220E17FCCABCC409FCA6948BE9529A60FFF57A`. It is licensed under the BSD license; see the vendor license file. The independent Python verification dependencies live only under `test-output\python-deps` and are not needed to run FilmDesk.

The app's errors are logged under `Scans\errors.log`.

## References

The installed Canon MG8100 English manual was inspected at `C:\Program Files (x86)\Canon\IJ Manual\CANON MG8100 SERIES\English\SG`:

- `Sg-003.html`: placing 35mm film and slides
- `Sg-206.html`: scanning film in Advanced Mode
- `Sg-604.html`: WIA does not support film
- `Sg-810.html`: 48/16-bit output
- `Sg-812.html`: Quiet Mode and film calibration

The TWAIN structure definitions were verified against the official [TWAIN 1.9 header](https://github.com/twain/twain-specification/blob/master/versions/1.9/twain.h), saved unchanged in `reference\twain.h`. Public product information: [Canon PIXMA MG8120](https://www.usa.canon.com/support/p/pixma-mg8120).
