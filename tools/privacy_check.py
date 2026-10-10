"""Reject unreviewed files, identifying metadata and recognizable credentials."""
from pathlib import Path, PurePosixPath
import hashlib
import json
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
NEUTRAL_NAME = "Negative Film Contributor"
NEUTRAL_EMAIL = "contributor@example.invalid"
HOME_PATH = re.compile(rb"(?i)(?:[a-z]:[\\/]users[\\/][^\s\"'<>]+|/(?:home|Users)/[^\s\"'<>]+)")
SECRET_PATTERNS = [
    re.compile(rb"(?:gh[pousr]_)[A-Za-z0-9]{30,}"),
    re.compile(rb"github_pat_[A-Za-z0-9_]{40,}"),
    re.compile(rb"AKIA[0-9A-Z]{16}"),
    re.compile(rb"sk-(?:proj-)?[A-Za-z0-9_-]{30,}"),
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(rb"(?i)https?://[^\s/@:]+:[^\s/@]+@"),
    re.compile(rb"(?i)(?:password|api[_-]?key|access[_-]?token|client[_-]?secret)\s*[:=]\s*[\"'][A-Za-z0-9_+/=.-]{16,}[\"']"),
]
TEXT_EXTENSIONS = {".py", ".cs", ".ps1", ".cmd", ".md", ".txt", ".json", ".xmp", ".config"}
PRIVATE_PARTS = {".git", ".venv", "venv", "node_modules", "local-data", "local-verification", "test-output", "results", "scans", "samples", "output", "input", "update-backups", "__pycache__"}


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, stderr=subprocess.PIPE)


def lines(value):
    return value.decode("utf-8").splitlines()


def scan_data(label, data, identifiers, errors):
    if HOME_PATH.search(data):
        errors.add(label + ": personal home path")
    folded = data.decode("utf-8", errors="replace").casefold()
    if any(identifier in folded for identifier in identifiers):
        errors.add(label + ": known personal identifier")
    if any(pattern.search(data) for pattern in SECRET_PATTERNS):
        errors.add(label + ": possible credential")


def scan_tree(reference, allowlist, assets, identifiers, errors):
    if reference == ":":
        entries = git("ls-files", "--stage", "-z").split(b"\0")
        entries = [entry.split(b"\t", 1) for entry in entries if entry]
        entries = [(metadata.split()[0], metadata.split()[1], path) for metadata, path in entries]
    else:
        records = git("ls-tree", "-r", "-z", reference).split(b"\0")
        entries = []
        for record in records:
            if record:
                metadata, path = record.split(b"\t", 1)
                mode, kind, oid = metadata.split()
                entries.append((mode, oid, path))
    for mode, oid, encoded_path in entries:
        path = encoded_path.decode("utf-8")
        label = ("staged" if reference == ":" else reference[:12]) + "/" + path
        scan_data(label + "/filename", encoded_path, identifiers, errors)
        parts = PurePosixPath(path).parts
        if any(part.casefold() in PRIVATE_PARTS or part.casefold().startswith(".env") for part in parts):
            errors.add(label + ": private runtime or data path")
            continue
        if path not in allowlist:
            errors.add(label + ": outside publication allowlist")
            continue
        if mode not in (b"100644", b"100755"):
            errors.add(label + ": symlink or embedded repository is prohibited")
            continue
        data = git("cat-file", "blob", oid.decode("ascii"))
        scan_data(label, data, identifiers, errors)
        if path in assets:
            if hashlib.sha256(data).hexdigest() != assets[path]:
                errors.add(label + ": UI asset differs from approved upstream bytes")
        elif PurePosixPath(path).suffix not in TEXT_EXTENSIONS and PurePosixPath(path).name != "LICENSE" and not path.startswith(".githooks/") and path not in {".gitignore", ".gitattributes"}:
            errors.add(label + ": unapproved file type")
        elif b"\0" in data:
            errors.add(label + ": unexpected binary content")
    return len(entries)


def main():
    identifiers_path = ROOT / ".privacy-identifiers.json"
    if not identifiers_path.is_file():
        raise RuntimeError("Local privacy identifiers are missing; configure them before committing or pushing.")
    identifiers = [value.casefold() for value in json.loads(identifiers_path.read_text(encoding="utf-8")) if len(value) >= 4]
    if not identifiers:
        raise RuntimeError("Local privacy identifier list is empty.")
    # Read controls from the actual index, not unstaged working-tree changes.
    allowlist = set(lines(git("show", ":publication-files.txt")))
    assets = json.loads(git("show", ":public-assets.json"))
    errors = set()
    for key, expected in (("user.name", NEUTRAL_NAME), ("user.email", NEUTRAL_EMAIL)):
        if git("config", "--local", "--get", key).decode("utf-8").strip() != expected:
            errors.add("Git configuration: non-neutral " + key)
    # Includes environment-variable overrides such as GIT_AUTHOR_EMAIL.
    for kind in ("AUTHOR", "COMMITTER"):
        identity = git("var", "GIT_" + kind + "_IDENT").decode("utf-8")
        if not identity.startswith(f"{NEUTRAL_NAME} <{NEUTRAL_EMAIL}> "):
            errors.add("Effective Git " + kind.lower() + " identity is non-neutral")
    count = scan_tree(":", allowlist, assets, identifiers, errors)
    commits = lines(git("rev-list", "--all"))
    for commit in commits:
        metadata = git("show", "-s", "--format=%an%n%ae%n%cn%n%ce%n%B", commit)
        values = lines(metadata)
        if values[:4] != [NEUTRAL_NAME, NEUTRAL_EMAIL, NEUTRAL_NAME, NEUTRAL_EMAIL]:
            errors.add(commit[:12] + ": non-neutral author or committer")
        scan_data(commit[:12] + "/metadata", metadata, identifiers, errors)
        scan_tree(commit, allowlist, assets, identifiers, errors)
    if errors:
        print("Privacy check failed:")
        for error in sorted(errors):
            print("- " + error)
        return 1
    print(f"Privacy check passed: {count} staged files, {len(commits)} reachable commits, {len(assets)} approved UI assets.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError, OSError, subprocess.CalledProcessError) as error:
        print("Privacy check could not complete: " + str(error), file=sys.stderr)
        raise SystemExit(2)
