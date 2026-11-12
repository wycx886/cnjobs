"""Check the Git index and historical paths before sharing the public framework."""
import re
import subprocess
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_FILES = frozenset({
    ".gitignore", "AGENTS.md", "README.md",
    "LICENSE", "LICENSE.md",
    "index.html",
    "package.json", "cordis.patch.yml",
})
PUBLIC_DIRS = frozenset({
    ".github", "data", "skills", "tools",
    "lib",
})
HISTORICAL_DIRS = frozenset({"catalog", "docs", "schemas", "scripts", "templates", "tests", "companies", "investors", "exports"})
RETIRED_INDEXES = frozenset({"data/targets.json", "data/investor-index.json"})
PRIVATE_PARTS = frozenset({
    "workspace", "workspace.local.json", "resume", "applications", "application", "local", "private", "resumes", "drafts",
    ".venv", "__pycache__", ".git",
})
# Public web URLs legitimately contain path segments such as /home/about;
# strip them before matching so only real local paths are reported.
URL_PATTERN = re.compile(rb"https?://[^\s\"'<>\\]+")
CONTENT_PATTERNS = (
    ("absolute home-directory path", re.compile(rb"/(?:Users|home)/[^/\s\x00]+/")),
    ("private key", re.compile(rb"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----")),
    ("GitHub credential", re.compile(rb"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})\b")),
    ("API credential", re.compile(rb"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{32,}\b")),
)
# Only the home-directory rule ignores URLs; credentials are never excused.
URL_INSENSITIVE = {"absolute home-directory path"}


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args])


def path_problem(name, historical=False):
    parts = PurePosixPath(name).parts
    folded = [part.casefold() for part in parts]
    if any(part in PRIVATE_PARTS or part == ".env" or part.startswith(".env.") for part in folded):
        return "private workspace or environment file"
    if PurePosixPath(name).suffix.casefold() in {".eml", ".msg", ".pem", ".key", ".p12"}:
        return "personal message or credential file"
    if not historical and (name.startswith(('data/investors/', 'data/views/investors/')) or name == 'data/platforms.json'):
        return "retired split layout; use companies and data/lists"
    if not historical and name in RETIRED_INDEXES:
        return "retired generated index; use data/index.json"
    if name in PUBLIC_FILES or (len(parts) > 1 and parts[0] in PUBLIC_DIRS):
        return None
    if historical and (name in {"taxonomy.md", "requirements-dev.txt"} or (len(parts) > 1 and parts[0] in HISTORICAL_DIRS)):
        return None
    return "outside the shared file allowlist"


def audit(root=ROOT):
    """Return problems without printing private contents or changing the index."""
    root = Path(root).resolve()
    actual_root = Path(git(root, "rev-parse", "--show-toplevel").decode("utf-8").strip()).resolve()
    if actual_root != root:
        return ["Repository root mismatch: refusing to share a parent workspace. Use this project's own Git repository."]
    problems = []
    seen_blobs = set()
    for entry in git(root, "ls-files", "--stage", "-z").split(b"\0"):
        if not entry:
            continue
        metadata, raw_name = entry.split(b"\t", 1)
        mode, oid, stage = metadata.decode("ascii").split()
        name = raw_name.decode("utf-8", errors="replace")
        reason = path_problem(name)
        if reason:
            problems.append("Index: %s (%s)" % (name, reason))
            continue
        if stage != "0" or mode not in {"100644", "100755"}:
            problems.append("Index: %s (unmerged entry, symlink or submodule)" % name)
            continue
        if oid not in seen_blobs:
            content = git(root, "cat-file", "blob", oid)
            for label, pattern in CONTENT_PATTERNS:
                haystack = URL_PATTERN.sub(b" ", content) if label in URL_INSENSITIVE else content
                if pattern.search(haystack):
                    problems.append("Index: %s (%s; content withheld)" % (name, label))
            seen_blobs.add(oid)
    # Ignore rules do not remove private files from earlier commits.
    history = git(root, "log", "--all", "--format=", "--name-only", "-z")
    historical_names = {name.decode("utf-8", errors="replace").strip("\n")
                        for name in history.split(b"\0") if name.strip(b"\n")}
    for name in sorted(historical_names):
        reason = path_problem(name, historical=True)
        if reason:
            problems.append("History: %s (%s)" % (name, reason))
    return problems


def require_public(root=ROOT):
    problems = audit(root)
    if problems:
        raise SystemExit("Sharing blocked:\n" + "\n".join(problems) +
                         "\nReview locally before committing or pushing. No contents were printed.")


if __name__ == "__main__":
    require_public()
    print("Sharing check passed: Git index and historical file paths follow the public boundary.")
