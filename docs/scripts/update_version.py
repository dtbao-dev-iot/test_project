#!/usr/bin/env python3
"""
Version update script for dtbao-IoT embedded C projects.

Updates PROJECT_VERSION_MAJOR/MINOR/PATCH/SUFFIX in fw and bl CMakeLists.txt,
and optionally the VERSION file.

Usage:
    # Manual: set fw and bl versions independently
    python docs/scripts/update_version.py "fw V24.00.01 bl V24.00.01_rc01"

    # Set both to same version
    python docs/scripts/update_version.py --both V24.00.01

    # Set only fw or bl
    python docs/scripts/update_version.py --fw V24.00.01
    python docs/scripts/update_version.py --bl V24.00.01_rc01

    # Auto-bump: official release (minor++, patch=00, suffix="")
    python docs/scripts/update_version.py --release

    # Auto-bump: pre-test (patch++, auto-increment _rc suffix)
    python docs/scripts/update_version.py --pretest

    # Auto-bump both workspaces independently
    python docs/scripts/update_version.py --release --fw-only
    python docs/scripts/update_version.py --pretest --bl-only

Options:
    --version-file    Also update the VERSION file
    --dry-run         Show what would change without writing
    --fw-only         Only update firmware CMakeLists
    --bl-only         Only update bootloader CMakeLists
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
FW_CMAKE = PROJECT_ROOT / "workspaces" / "app_firmware" / "CMakeLists.txt"
BL_CMAKE = PROJECT_ROOT / "workspaces" / "app_bootloader" / "CMakeLists.txt"
VERSION_FILE = PROJECT_ROOT / "VERSION"


# ---------------------------------------------------------------------------
# Version dataclass
# ---------------------------------------------------------------------------


@dataclass
class Version:
    major: str
    minor: str
    patch: str
    suffix: str  # e.g. "" or "_rc01"

    @property
    def base(self) -> str:
        return f"V{self.major}.{self.minor}.{self.patch}"

    @property
    def full(self) -> str:
        return f"{self.base}{self.suffix}"

    @property
    def cmake_ver(self) -> str:
        """Return the cmake PROJECT_VER format: v26.05.00 or v26.05.00_rc01."""
        return f"v{self.major}.{self.minor}.{self.patch}{self.suffix}"

    def __str__(self) -> str:
        return self.full

    def bump_release(self) -> Version:
        """Official release: minor++, patch=00, suffix=''.
        E.g. V26.05.00 -> V26.06.00
             V26.05.00_rc03 -> V26.06.00
        """
        new_minor = int(self.minor) + 1
        return Version(self.major, f"{new_minor:02d}", "00", "")

    def bump_pretest(self) -> Version:
        """Pre-test: keep base version, auto-increment _rc suffix.
        If no suffix: add _rc01.
        If suffix _rcNN: increment to _rc(NN+1).
        E.g. V26.05.00       -> V26.05.00_rc01
             V26.05.00_rc01  -> V26.05.00_rc02
        """
        rc_match = re.match(r"^_rc(\d+)$", self.suffix)
        if rc_match:
            new_rc = int(rc_match.group(1)) + 1
            return Version(self.major, self.minor, self.patch, f"_rc{new_rc:02d}")
        return Version(self.major, self.minor, self.patch, "_rc01")


# ---------------------------------------------------------------------------
# CMakeLists.txt parsing / writing
# ---------------------------------------------------------------------------


def read_version_from_cmake(cmake_path: Path) -> Version:
    """Read PROJECT_VERSION_MAJOR/MINOR/PATCH/SUFFIX from a CMakeLists.txt."""
    content = cmake_path.read_text(encoding="utf-8")

    def extract(var: str) -> str:
        pattern = rf'set\({var}\s+"([^"]*)"\)'
        match = re.search(pattern, content)
        if not match:
            log_error(f"Could not find {var} in {cmake_path}")
            sys.exit(1)
        return match.group(1)

    major = extract("PROJECT_VERSION_MAJOR")
    minor = extract("PROJECT_VERSION_MINOR")
    patch = extract("PROJECT_VERSION_PATCH")

    # Suffix uses the "if(NOT DEFINED ..." pattern with default ""
    suffix_pattern = r'set\(PROJECT_VERSION_SUFFIX\s+"([^"]*)"\)'
    suffix_match = re.search(suffix_pattern, content)
    suffix = suffix_match.group(1) if suffix_match else ""

    return Version(major, minor, patch, suffix)


def write_version_to_cmake(cmake_path: Path, version: Version) -> None:
    """Write version fields back into a CMakeLists.txt file.

    Only updates PROJECT_VERSION_MAJOR/MINOR/PATCH/SUFFIX.
    PROJECT_VER is computed by CMake from those variables, so no update needed.
    """
    content = cmake_path.read_text(encoding="utf-8")

    old = read_version_from_cmake(cmake_path)

    for var, old_val, new_val in [
        ("PROJECT_VERSION_MAJOR", old.major, version.major),
        ("PROJECT_VERSION_MINOR", old.minor, version.minor),
        ("PROJECT_VERSION_PATCH", old.patch, version.patch),
        ("PROJECT_VERSION_SUFFIX", old.suffix, version.suffix),
    ]:
        pattern = rf'set\({var}\s+"{re.escape(old_val)}"\)'
        replacement = f'set({var} "{new_val}")'
        content, count = re.subn(pattern, replacement, content)
        if count == 0:
            log_error(f"Could not find set({var} \"{old_val}\") in {cmake_path}")
            sys.exit(1)

    cmake_path.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# VERSION file
# ---------------------------------------------------------------------------


def read_version_file() -> str:
    """Read the VERSION file content."""
    if not VERSION_FILE.exists():
        return ""
    return VERSION_FILE.read_text(encoding="utf-8").strip()


def write_version_file(version: Version) -> None:
    """Write version to the VERSION file."""
    VERSION_FILE.write_text(version.full + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Input parsing
# ---------------------------------------------------------------------------


def parse_version_string(s: str) -> Version:
    """Parse a version string like 'V24.00.01' or 'V24.00.01_rc01'."""
    match = re.match(r"^V(\d{2})\.(\d{2})\.(\d{2})(_rc\d+)?$", s)
    if not match:
        log_error(f"Invalid version format: '{s}'. Expected VXX.YY.ZZ[_rcNN]")
        sys.exit(1)
    suffix = match.group(4) or ""
    return Version(match.group(1), match.group(2), match.group(3), suffix)


def parse_manual_input(text: str) -> dict[str, Version]:
    """Parse manual input like 'fw V24.00.01 bl V24.00.01_rc01'.

    Returns dict with 'fw' and/or 'bl' keys.
    """
    result: dict[str, Version] = {}
    pattern = r"(fw|bl)\s+(V\d{2}\.\d{2}\.\d{2}(?:_rc\d+)?)"
    for match in re.finditer(pattern, text):
        target = match.group(1)
        version = parse_version_string(match.group(2))
        result[target] = version

    if not result:
        # Try treating the whole string as a version for both
        version = parse_version_string(text.strip())
        result["fw"] = version
        result["bl"] = version

    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def log(msg: str) -> None:
    print(f"[version] {msg}")


def log_error(msg: str) -> None:
    print(f"[version] ERROR: {msg}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Update firmware/bootloader version in CMakeLists.txt",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Manual input: positional or --fw/--bl/--both
    parser.add_argument(
        "manual",
        nargs="?",
        default=None,
        help='Manual version input, e.g. "fw V24.00.01 bl V24.00.01_rc01"',
    )
    parser.add_argument("--fw", type=str, help="Set firmware version (e.g. V24.00.01)")
    parser.add_argument("--bl", type=str, help="Set bootloader version (e.g. V24.00.01_rc01)")
    parser.add_argument(
        "--both", type=str, help="Set both fw and bl to the same version"
    )

    # Auto-bump modes
    bump = parser.add_mutually_exclusive_group()
    bump.add_argument(
        "--release",
        action="store_true",
        help="Auto-bump: official release (minor++, patch=00, suffix='')",
    )
    bump.add_argument(
        "--pretest",
        action="store_true",
        help="Auto-bump: pre-test (add/increment _rc suffix)",
    )

    # Scope
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument(
        "--fw-only", action="store_true", help="Only update firmware CMakeLists"
    )
    scope.add_argument(
        "--bl-only", action="store_true", help="Only update bootloader CMakeLists"
    )

    # Options
    parser.add_argument(
        "--version-file",
        action="store_true",
        help="Also update the VERSION file (uses fw version)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without writing files",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    log("=" * 50)
    log("dtbao-IoT Version Update")
    log("=" * 50)

    # --- Read current versions ---
    fw_version = read_version_from_cmake(FW_CMAKE)
    bl_version = read_version_from_cmake(BL_CMAKE)

    log(f"Current fw: {fw_version}")
    log(f"Current bl: {bl_version}")

    # --- Determine target versions ---
    new_fw: Optional[Version] = None
    new_bl: Optional[Version] = None

    # Manual input from positional argument
    if args.manual:
        parsed = parse_manual_input(args.manual)
        if "fw" in parsed:
            new_fw = parsed["fw"]
        if "bl" in parsed:
            new_bl = parsed["bl"]
        # If only one target specified in manual, apply to both
        if new_fw and not new_bl and "bl" not in parsed:
            new_bl = new_fw
        if new_bl and not new_fw and "fw" not in parsed:
            new_fw = new_bl

    # --fw / --bl / --both override manual
    if args.fw:
        new_fw = parse_version_string(args.fw)
    if args.bl:
        new_bl = parse_version_string(args.bl)
    if args.both:
        new_fw = parse_version_string(args.both)
        new_bl = parse_version_string(args.both)

    # Auto-bump modes
    if args.release:
        if not new_fw:
            new_fw = fw_version.bump_release()
        if not new_bl:
            new_bl = bl_version.bump_release()

    if args.pretest:
        if not new_fw:
            new_fw = fw_version.bump_pretest()
        if not new_bl:
            new_bl = bl_version.bump_pretest()

    # If nothing specified, show current versions and exit
    if not new_fw and not new_bl:
        log("No version changes specified. Use --release, --pretest, or manual input.")
        log("")
        log("Examples:")
        log('  python docs/scripts/update_version.py "fw V24.00.01 bl V24.00.01_rc01"')
        log("  python docs/scripts/update_version.py --both V24.00.01")
        log("  python docs/scripts/update_version.py --release")
        log("  python docs/scripts/update_version.py --pretest")
        sys.exit(0)

    # --- Apply scope ---
    update_fw = True
    update_bl = True
    if args.fw_only:
        update_bl = False
        new_bl = None
    if args.bl_only:
        update_fw = False
        new_fw = None

    # --- Display changes ---
    log("")
    log("Planned changes:")
    if new_fw and update_fw:
        log(f"  fw: {fw_version} -> {new_fw}")
    if new_bl and update_bl:
        log(f"  bl: {bl_version} -> {new_bl}")
    if args.version_file and (new_fw or new_bl):
        ver_for_file = new_fw or new_bl
        old_ver_file = read_version_file() or "(none)"
        log(f"  VERSION: {old_ver_file} -> {ver_for_file}")

    if args.dry_run:
        log("")
        log("(dry-run) No files were modified.")
        return

    # --- Apply changes ---
    if new_fw and update_fw:
        write_version_to_cmake(FW_CMAKE, new_fw)
        log(f"  Updated {FW_CMAKE.relative_to(PROJECT_ROOT)}")

    if new_bl and update_bl:
        write_version_to_cmake(BL_CMAKE, new_bl)
        log(f"  Updated {BL_CMAKE.relative_to(PROJECT_ROOT)}")

    if args.version_file and (new_fw or new_bl):
        ver_for_file = new_fw or new_bl
        write_version_file(ver_for_file)
        log(f"  Updated {VERSION_FILE.relative_to(PROJECT_ROOT)}")

    # --- Verify ---
    log("")
    log("Verification:")
    if new_fw and update_fw:
        verify_fw = read_version_from_cmake(FW_CMAKE)
        log(f"  fw: {verify_fw}")
    if new_bl and update_bl:
        verify_bl = read_version_from_cmake(BL_CMAKE)
        log(f"  bl: {verify_bl}")

    log("")
    log("Done.")


if __name__ == "__main__":
    main()