#!/usr/bin/env python3
"""
Release script for dtbao-IoT embedded C projects.

Usage:
    python scripts/release.py

Workflow:
    1. Validates working directory is clean
    2. Prompts for new version
    3. Validates CHANGELOG entry exists
    4. Updates VERSION file and version.h
    5. Updates README.md badge
    6. Commits, pushes branch, tags, pushes tag -> triggers GitHub Actions release
"""

import re
import subprocess
import sys
from pathlib import Path

# ─── Project configuration (set during project setup) ────────────────────────
# PROJECT_TYPE: "firmware-dev"  -> version format VYY.MM.PP, tag V26.04.00
#               "firmware-libs" -> version format MAJOR.MINOR.PATCH, tag v1.0.0
PROJECT_TYPE = "firmware-dev"
# ─────────────────────────────────────────────────────────────────────────────

REPO_DIR = Path(__file__).parent.parent

if PROJECT_TYPE == "firmware-dev":
    VERSION_PATTERN   = re.compile(r"^V\d{2}\.\d{2}\.\d{2}$")
    VERSION_HEADER    = REPO_DIR / "configs_tool" / "version.h"
    MAJOR_DEFINE      = "FW_VERSION_MAJOR"
    MINOR_DEFINE      = "FW_VERSION_MINOR"
    PATCH_DEFINE      = "FW_VERSION_PATCH"
    STRING_DEFINE     = "FW_VERSION_STRING"
    VERSION_HINT      = "VXX.YY.ZZ  (e.g. V26.04.00)"

else:  # firmware-libs
    VERSION_PATTERN   = re.compile(r"^\d+\.\d+\.\d+$")
    VERSION_HEADER    = REPO_DIR / "inc" / "version.h"
    MAJOR_DEFINE      = "LIB_VERSION_MAJOR"
    MINOR_DEFINE      = "LIB_VERSION_MINOR"
    PATCH_DEFINE      = "LIB_VERSION_PATCH"
    STRING_DEFINE     = "LIB_VERSION_STRING"
    VERSION_HINT      = "MAJOR.MINOR.PATCH  (e.g. 1.2.0)"

VERSION_FILE    = REPO_DIR / "VERSION"
CHANGELOG_DIR   = REPO_DIR / "docs" / "CHANGELOG"


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=REPO_DIR, check=check, capture_output=True, text=True)


def current_version() -> str:
    return VERSION_FILE.read_text(encoding="utf-8").strip()


def current_branch() -> str:
    return run(["git", "rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()


def tag_name(version: str) -> str:
    """Return the git tag string for a version."""
    if PROJECT_TYPE == "firmware-libs":
        return f"v{version}"
    return version  # firmware-dev version already starts with V


def check_git_clean() -> None:
    result = run(["git", "status", "--porcelain"])
    changes = [l for l in result.stdout.splitlines() if not l.startswith("??")]
    if changes:
        print("ERROR: Working directory has uncommitted changes. Commit or stash them first.")
        print("\n".join(changes))
        sys.exit(1)


def check_tag_exists(tag: str) -> None:
    result = run(["git", "tag", "--list", tag])
    if result.stdout.strip():
        print(f"ERROR: Tag '{tag}' already exists.")
        sys.exit(1)


def check_changelog(version: str) -> Path:
    changelog = CHANGELOG_DIR / f"{version}.md"
    if not changelog.exists():
        print(f"ERROR: docs/CHANGELOG/{version}.md not found.")
        print( "       Create the changelog file before releasing.")
        sys.exit(1)
    return changelog


def prompt_version() -> str:
    current = current_version()
    print(f"Current version : {current}")
    print(f"Format required : {VERSION_HINT}")
    print()

    while True:
        version = input("New version     : ").strip()
        if not VERSION_PATTERN.match(version):
            print(f"  ERROR: '{version}' does not match {VERSION_HINT} -- try again.")
            continue
        if version == current:
            print(f"  ERROR: '{version}' is the same as the current version -- try again.")
            continue
        return version


def parse_version(version: str) -> tuple[str, str, str]:
    """Return (major, minor, patch) strings."""
    if PROJECT_TYPE == "firmware-dev":
        # VYY.MM.PP  ->  strip leading V
        parts = version.lstrip("V").split(".")
    else:
        parts = version.split(".")
    return parts[0], parts[1], parts[2]


def update_version_header(version: str) -> None:
    major, minor, patch = parse_version(version)
    if not VERSION_HEADER.exists():
        print(f"  WARN version.h not found at {VERSION_HEADER} -- skipped.")
        return

    content = VERSION_HEADER.read_text(encoding="utf-8")

    content = re.sub(
        rf"(#define\s+{MAJOR_DEFINE}\s+)\S+",
        rf"\g<1>{major}",
        content,
    )
    content = re.sub(
        rf"(#define\s+{MINOR_DEFINE}\s+)\S+",
        rf"\g<1>{minor}",
        content,
    )
    content = re.sub(
        rf"(#define\s+{PATCH_DEFINE}\s+)\S+",
        rf"\g<1>{patch}",
        content,
    )
    content = re.sub(
        rf'(#define\s+{STRING_DEFINE}\s+)".+"',
        rf'\g<1>"{major}.{minor}.{patch}"',
        content,
    )

    VERSION_HEADER.write_text(content, encoding="utf-8")
    print(f"  OK  Updated {VERSION_HEADER.relative_to(REPO_DIR)}: {major}.{minor}.{patch}")


def update_readme_badge(old_version: str, new_version: str) -> None:
    readme = REPO_DIR / "README.md"
    if not readme.exists():
        print("  WARN README.md not found -- badge update skipped.")
        return

    content = readme.read_text(encoding="utf-8")
    old_badge = f"version-{old_version}-blue"
    new_badge = f"version-{new_version}-blue"

    if old_badge not in content:
        print(f"  WARN README.md badge not found for {old_version} -- skipped.")
        return

    readme.write_text(content.replace(old_badge, new_badge, 1), encoding="utf-8")
    print(f"  OK  Updated README.md badge: {old_version} -> {new_version}")


def confirm(version: str, tag: str, branch: str, changelog: Path) -> None:
    rel_changelog = changelog.relative_to(REPO_DIR)
    version_h_rel = VERSION_HEADER.relative_to(REPO_DIR) if VERSION_HEADER.exists() else "version.h (not found)"
    print()
    print("-" * 50)
    print(f"  Version      : {version}")
    print(f"  Tag          : {tag}")
    print(f"  Commit msg   : chore: release {version}")
    print(f"  Files staged : VERSION  README.md  {rel_changelog}  {version_h_rel}")
    print(f"  Push branch  : git push origin {branch}")
    print(f"  Push tag     : git push origin {tag}")
    print("-" * 50)
    answer = input("Proceed? (yes / no): ").strip().lower()
    if answer != "yes":
        print("Aborted.")
        sys.exit(0)


def main() -> None:
    print("=== dtbao-IoT Release ===")
    print(f"    Project type : {PROJECT_TYPE}")
    print()

    check_git_clean()

    old_version = current_version()
    version     = prompt_version()
    tag         = tag_name(version)
    branch      = current_branch()

    check_tag_exists(tag)
    changelog = check_changelog(version)
    confirm(version, tag, branch, changelog)

    print()

    # Update VERSION file
    VERSION_FILE.write_text(version + "\n", encoding="utf-8")
    print(f"  OK  Updated VERSION: {version}")

    # Update version.h
    update_version_header(version)

    # Update README.md badge
    update_readme_badge(old_version, version)

    # Stage files and commit
    files_to_stage = [
        "VERSION",
        "README.md",
        str(changelog.relative_to(REPO_DIR)),
        str(VERSION_HEADER.relative_to(REPO_DIR)) if VERSION_HEADER.exists() else None,
    ]
    files_to_stage = [f for f in files_to_stage if f is not None]
    run(["git", "add"] + files_to_stage)
    run(["git", "commit", "-m", f"chore: release {version}"])
    print(f"  OK  Committed release files")

    # Push branch
    run(["git", "push", "origin", branch])
    print(f"  OK  Pushed branch: {branch}")

    # Tag and push tag -> triggers GitHub Actions release
    run(["git", "tag", tag])
    print(f"  OK  Tagged: {tag}")

    run(["git", "push", "origin", tag])
    print(f"  OK  Pushed tag: {tag}")

    print()
    print(f"Release {version} triggered. GitHub Actions will create the GitHub Release automatically.")


if __name__ == "__main__":
    main()