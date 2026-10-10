# Project-local dependencies

The installed applications in the original workspace continue to use their existing runtimes. This source snapshot intentionally excludes executable applications, virtual environments, models, and private input fixtures.

- **FreeCCR / NegativeLab:** use Python 3.12 in `FreeCCR/.venv`, install `FreeCCR/requirements.txt`, plus Pillow and pytest 8.3.5. The local FreeCCR launch helpers explicitly require an RTX 4080 GPU and fail if it is unavailable. Preserve that behavior unless deliberately adapting the GPU configuration.
- **SwinIR:** use a separate `SwinIR/.venv`, its dependency manifests, and `download_model.py`. `SwinIR/LOCAL_SETUP.md` describes its project-local setup.
- **darktable:** supply the compatible darktable 5.6.1 portable files in `darktable/app/`. NegativeLab expects `darktable/app/bin/darktable-cli.exe` and its corresponding runtime data. Its XMP template depends on that version's module layouts.
- **FilmDesk:** requires the Windows .NET Framework compiler, the installed compatible 32-bit Canon TWAIN driver, and BitMiracle.LibTiff.NET **2.4.660**. Place the package's `lib/netstandard2.0/BitMiracle.LibTiff.NET.dll` at `ScanDesk/vendor/libtiff/lib/netstandard2.0/BitMiracle.LibTiff.NET.dll`, then run `ScanDesk/build.ps1`. Obtain the package from the [official NuGet package](https://www.nuget.org/packages/BitMiracle.LibTiff.NET/2.4.660) and retain its license locally.

Verified LibTiff.NET DLL SHA-256:

```text
0cfdba77f76af11c4dfa0a465a9155f7e8aac5632b54118b9b20ba185c58cd50
```

NegativeLab's unit tests generate synthetic TIFF/JPEG inputs. Its optional GUI/converter and GPU smoke scripts additionally expect a locally supplied `Samples/Signynt/Example.tif`; that fixture is not included. ScanDesk diagnostics save their reports locally. Scanner acquisition requires the user's explicit hardware setup and quiet-mode check.
