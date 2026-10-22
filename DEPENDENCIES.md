# Project-local dependencies

The installed applications in the original workspace continue to use their existing runtimes. This source snapshot intentionally excludes executable applications, virtual environments, models, and private input fixtures.

## Python certificate security

The [October 2026 Python security notice](https://discuss.python.org/t/information-for-python-users-regarding-emudhra-emsign-ca-certificate-security-incident/109576)
requires pip 26.2.2 or newer and certifi 2026.10.19 or newer following the
emSign certificate-authority incident. Pip bundles its own certifi, so updating
standalone certifi or the operating system alone does not update pip's bundle.
The application requirements enforce the certifi minimum; SwinIR's lockfile
records the tested certifi 2026.10.19 release.

After creating either Python 3.12 environment, and when updating an existing
environment, bootstrap pip before installing other dependencies. Run this from
the repository root once the corresponding `.venv` directories exist:

```powershell
$pipWheel = 'pip @ https://files.pythonhosted.org/packages/3f/06/3e4420302363fbb71be3c7f35ce042f54bfca330e3e66b3a2e3c4cca579f/pip-26.2.2-py3-none-any.whl#sha256=fd7f4dfa8190e014013b9f08f3e973f4e4c26ffd179a204895533a7254813a70'
$interpreters = @('.\FreeCCR\.venv\Scripts\python.exe', '.\SwinIR\.venv\Scripts\python.exe')
foreach ($interpreter in $interpreters) {
    & $interpreter -m pip install --upgrade --no-deps $pipWheel
    if ($LASTEXITCODE -ne 0) { throw "Secure pip bootstrap failed: $interpreter" }
    & $interpreter -m pip install --upgrade 'certifi>=2026.10.19'
    if ($LASTEXITCODE -ne 0) { throw "Certificate update failed: $interpreter" }
    & $interpreter -m pip check
    if ($LASTEXITCODE -ne 0) { throw "Dependency check failed: $interpreter" }
}
```

The direct URL and SHA-256 come from the notice and protect the initial pip
download even when the old pip bundle is affected. Both environments need their
own update; NegativeLab shares FreeCCR's environment. Newly created environments
can inherit an older pip from Python's `ensurepip`, so repeat this bootstrap
when recreating an environment. These commands change only the selected virtual
environments. Host-specific trust settings and certificate overrides are not
distributed in this source snapshot.

## Application dependencies

- **FreeCCR / NegativeLab:** use Python 3.12 in `FreeCCR/.venv`, install `FreeCCR/requirements.txt`, plus Pillow and pytest 8.3.5. The local FreeCCR launch helpers explicitly require an RTX 4080 GPU and fail if it is unavailable. Preserve that behavior unless deliberately adapting the GPU configuration.
- **SwinIR:** use a separate `SwinIR/.venv`, its dependency manifests, and `download_model.py`. `SwinIR/LOCAL_SETUP.md` describes its project-local setup.
- **darktable:** supply the compatible darktable 5.6.1 portable files in `darktable/app/`. NegativeLab expects `darktable/app/bin/darktable-cli.exe` and its corresponding runtime data. Its XMP template depends on that version's module layouts.
- **FilmDesk:** requires the Windows .NET Framework compiler, the installed compatible 32-bit Canon TWAIN driver, and BitMiracle.LibTiff.NET **2.4.660**. Place the package's `lib/netstandard2.0/BitMiracle.LibTiff.NET.dll` at `ScanDesk/vendor/libtiff/lib/netstandard2.0/BitMiracle.LibTiff.NET.dll`, then run `ScanDesk/build.ps1`. Obtain the package from the [official NuGet package](https://www.nuget.org/packages/BitMiracle.LibTiff.NET/2.4.660) and retain its license locally.

Verified LibTiff.NET DLL SHA-256:

```text
0cfdba77f76af11c4dfa0a465a9155f7e8aac5632b54118b9b20ba185c58cd50
```

NegativeLab's unit tests generate synthetic TIFF/JPEG inputs. Its optional GUI/converter and GPU smoke scripts additionally expect a locally supplied `Samples/Signynt/Example.tif`; that fixture is not included. ScanDesk diagnostics save their reports locally. Scanner acquisition requires the user's explicit hardware setup and quiet-mode check.
