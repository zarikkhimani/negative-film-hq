# Privacy review

## Prepared boundary

The GitHub destination was verified as private and without branches at preparation time. No upload, pull request, or repository visibility change was performed during this review.

The local copy contains selected application source, tests, dependency manifests, documentation, licenses, and nine UI assets verified against their upstream Git blobs. It contains no previous repository history.

The original workspace contains personal image outputs and diagnostic records with absolute Windows home paths. Its machine-specific setup notes and default Git author configuration also contain personal identifiers. Those notes, records, environments, catalogs, and photographs are excluded from this copy.

## Controls

- The exact file list in `publication-files.txt` is the publication allowlist. `.gitignore` excludes every other file by default.
- Only the nine upstream UI assets in `public-assets.json` are allowed as images; their hashes are checked.
- A repository-local neutral author name and placeholder email replace the inherited personal Git identity for future commits. Other repositories retain their existing configuration.
- Git's local commit and push hooks run `tools/privacy_check.py`. An unavailable scanner or interpreter stops the operation with an error.
- The scanner reads known personal identifiers from an ignored local file. The identifiers themselves are not committed.
- The check scans index contents, reachable commit trees, commit messages, and author/committer identities. It prints file locations and categories without printing matched secret values.

## Visibility limits

A GitHub repository URL and ownership information identify the owning account. People granted access can see that association. A GitHub-provided noreply email protects a real mailbox but includes the account username; the placeholder email used here contains no account username.

Public anonymity would require a separately chosen account/organization and careful review of its profile and activity. This preparation does not change account ownership or profile settings.

This check targets recognizable credentials, Windows/Unix home paths, known local identifiers, prohibited file classes, and the permitted UI assets. It cannot prove that all possible secrets or identifying details have been detected. It does not inspect or certify the entire computer or unrelated repositories.

The Code Review plugin operates on GitHub pull requests. The destination has no pull request to review; this preparation uses a local source and Git-metadata review.

## Validation

- 183 copied application/source/license/asset files match the original working files by SHA-256. The original FreeCCR and SwinIR changes are preserved in place.
- Nine UI assets match their upstream Git blobs. No other images are permitted.
- 140 Python source files parsed successfully; PowerShell preparation/source files parsed successfully.
- All 46 existing NegativeLab unit tests passed using the installed local runtime. Pytest reported two cache-directory permission warnings; test execution succeeded.
- Ten privacy-guard cases passed: safe source, home paths, personal identifiers, credentials, unapproved photos, environment identity overrides, historical identity, historical credentials, an unstaged allowlist change, and altered UI artwork.
- The staged snapshot passed the privacy scan and whitespace checks for the new preparation files.
- The private GitHub remote was reached using a read-only refs check. It was empty at verification time.

GUI/converter smoke tests, GPU inference, physical scanner acquisition, and a clean-machine dependency installation were not rerun for this source-only preparation. The copied application source is unchanged. The source snapshot requires the excluded local runtimes before those checks can run.
