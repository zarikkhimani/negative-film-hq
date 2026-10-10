# FilmDesk preferences

- This application is only for 35mm film scanning.
- Save scans automatically as lossless TIFF, with no extra save/export step or format choices. Rotated copies also use lossless TIFF. The user accepts TIFF or JPEG only; do not introduce PNG outputs.
- Scan and save without displaying or decoding an image preview in FilmDesk. Show the saved filename, location and metadata. Leave Canon's automatic startup preview disabled; its manual Preview remains available when needed to position scan regions.
- Prefer Quiet Mode for every preview and scan. Verify Canon's driver checkbox before hardware acquisition; the prototype cannot enforce or read it automatically yet.
- Use Whole Film Image view with manual scan regions, frame detection bypassed and available corrections disabled. Preserve negative colors unless the user requests conversion. At 4800 dpi, Canon's documented 30000-pixel height limit means a long strip may need two overlapping regions, each at most 6.25 inches tall; do not silently lower resolution.
- Default preservation preset: Color Positive Film, 35mm Strip, 4800 dpi on both axes, true 48-bit RGB, Flexible output at 100%, all available corrections None/OFF, Color Settings None, Quiet Mode checked. The user has also requested an optional 9600 dpi preset with the same settings. Label square 9600 dpi as exceeding the horizontal optical limit; only request it when selected. No 19200 dpi or enlargement. Validate actual DPI against the selected preset and never silently reduce bit depth or resolution.
- At 9600 dpi, the documented 30000-pixel height limit is 3.125 inches, but the 1.8 GB limit is tighter for the full approximately 1.22-inch width in 48-bit RGB. Use overlapping manual regions up to 2.5 inches tall at that width, or smaller regions as needed. Do not silently downsample or automatically detect frames.
- Preserve original scan files when producing converted, cropped, or rotated copies.
