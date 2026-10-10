# Negative Film HQ

Windows tools for scanning 35mm film, converting negatives, and optionally enlarging positive images.

- `ScanDesk/`: FilmDesk scanner source and tests.
- `NegativeLab/`: conversion interface, FreeCCR/Negadoctor adapter, optional SwinIR actions, and tests.
- `FreeCCR/`: current converter source, local launch helpers, tests, and upstream licenses.
- `SwinIR/`: model architecture, x2 runner, download helper, and dependency manifests.

This repository is a source snapshot. Photos, scans, results, catalogs, runtime settings, logs, screenshots, downloaded models, executable applications, virtual environments, and previous Git histories are excluded. UI artwork under `FreeCCR/src/icons/` is copied byte-for-byte from upstream and recorded in `public-assets.json`.

The existing applications use sibling folders and project-local runtimes. The source copy does not include those installed runtimes. See `DEPENDENCIES.md` before running it on another computer. The original working applications remain separate from this copy.

Run the privacy check with an available Python interpreter:

```powershell
python tools/privacy_check.py
```

It checks staged files and all reachable commits for prohibited files, personal home paths, known local identifiers, recognizable credentials, and non-neutral commit identities. New publishable files must be added deliberately to `publication-files.txt` and `.gitignore`. No scan can guarantee detection of every possible identifying detail or secret; review the actual staged files before sharing.

The configured Git remote identifies the owning GitHub account. Repository privacy controls access; it does not make that account anonymous to people with access. A neutral author name and placeholder email prevent personal commit metadata from being added, but those commits will not be attributed through an account email.

See `PRIVACY_REVIEW.md` for the current review and `THIRD_PARTY.md` for source provenance and licenses.
