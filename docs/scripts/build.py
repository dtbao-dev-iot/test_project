#!/usr/bin/env python3
"""
Build script for dtbao-IoT ESP-IDF embedded C projects.

Usage:
    python docs/scripts/build.py [OPTIONS]

Build modes (mutually exclusive):
    --all              Build firmware + bootloader then merge (default)
    --fw               Build only firmware workspace
    --bl               Build only bootloader workspace

Options:
    --clean            Full clean before build (idf.py fullclean)
    --reconfigure      Force reconfigure before build
    --build-type TYPE  Override build_type: "dev" or "release"
    --secure           Include sdkconfig.secure for bootloader build
    --config PATH      Path to config_workspace.json
    --ci               CI mode: auto-update config, verbose, non-interactive
    --verbose, -v      Verbose output (show all subprocess output)
    --output-dir DIR   Release output directory (default: workspaces/release)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
VERSION_FILE = PROJECT_ROOT / "VERSION"
CONFIG_FILE = PROJECT_ROOT / "configs_tool" / "config_workspace.json"
PARTITIONS_CSV = PROJECT_ROOT / "configs_tool" / "partitions.csv"
RELEASE_DIR = PROJECT_ROOT / "workspaces" / "release"
WORKSPACE_FW = PROJECT_ROOT / "workspaces" / "app_firmware"
WORKSPACE_BL = PROJECT_ROOT / "workspaces" / "app_bootloader"
SUPPORTED_TARGETS = ["esp32s3", "esp32", "esp32c3", "esp32c6", "esp32s2"]

PARTITION_TABLE_OFFSET = 0xF000

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def log(msg: str) -> None:
    print(f"[build] {msg}")


def log_error(msg: str) -> None:
    print(f"[build] ERROR: {msg}", file=sys.stderr)


def run_cmd(
    cmd: List[str],
    cwd: Optional[Path] = None,
    verbose: bool = False,
    check: bool = True,
) -> subprocess.CompletedProcess:
    """Run a command, optionally streaming output."""
    log(f"$ {' '.join(cmd)}")
    if verbose:
        result = subprocess.run(cmd, cwd=cwd, check=check, text=True)
    else:
        result = subprocess.run(
            cmd, cwd=cwd, check=check, capture_output=True, text=True
        )
    return result


def setup_idf_env(config: Dict) -> None:
    """Set IDF_PATH and activate ESP-IDF Python environment.

    Priority:
    1. Use idf_python_env from config if explicitly set
    2. Source export.bat/export.sh from idf_path
    """
    idf_path = config.get("idf_path", "")
    idf_python_env = config.get("idf_python_env", "")

    if idf_path:
        idf_dir = Path(idf_path)
        if not idf_dir.exists():
            log_error(f"IDF_PATH directory not found: {idf_path}")
            log_error("Check idf_path in config_workspace.json")
            sys.exit(1)
        os.environ["IDF_PATH"] = str(idf_dir)
        log(f"IDF_PATH set to: {idf_dir}")

    # Priority 1: explicitly configured Python env
    if idf_python_env:
        venv_dir = Path(idf_python_env)
        if not venv_dir.exists():
            log_error(f"ESP-IDF Python environment not found: {idf_python_env}")
            log_error("Check idf_python_env in config_workspace.json")
            sys.exit(1)
        _activate_python_env(venv_dir)
        return

    # Priority 2: source export script to activate ESP-IDF environment
    if idf_path:
        idf_dir = Path(idf_path)
        export_script = idf_dir / (
            "export.bat" if sys.platform == "win32" else "export.sh"
        )
        if export_script.exists():
            log(f"Activating ESP-IDF environment from {export_script.name}...")
            _source_idf_export(export_script)
            return

    log_error(
        "No ESP-IDF Python environment found. "
        "Set idf_python_env in config_workspace.json "
        "or ensure export.bat/export.sh is available."
    )
    sys.exit(1)


def _activate_python_env(venv_dir: Path) -> None:
    """Activate a Python virtual environment by adding it to PATH."""
    if sys.platform == "win32":
        scripts_dir = str(venv_dir / "Scripts")
    else:
        scripts_dir = str(venv_dir / "bin")
    os.environ["PATH"] = scripts_dir + os.pathsep + os.environ.get("PATH", "")
    os.environ["VIRTUAL_ENV"] = str(venv_dir)
    log(f"Python env activated: {venv_dir}")


def _source_idf_export(export_script: Path) -> None:
    """Source ESP-IDF export script and apply environment changes.

    Runs export.bat (Windows) or export.sh (Linux/Mac) in a subprocess,
    captures the resulting environment via JSON, and applies changes to os.environ.
    """
    old_env = dict(os.environ)

    # Create temp files (delete=False so subprocess can write to them)
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        env_json_path = Path(f.name)

    with tempfile.NamedTemporaryFile(
        suffix=".py", delete=False, mode="w", encoding="utf-8"
    ) as f:
        f.write(
            "import os, json\n"
            f'with open(r"{env_json_path}", "w") as f:\n'
            "    json.dump(dict(os.environ), f)\n"
        )
        helper_path = Path(f.name)

    wrapper_path: Optional[Path] = None

    try:
        if sys.platform == "win32":
            with tempfile.NamedTemporaryFile(
                suffix=".bat", delete=False, mode="w", encoding="utf-8"
            ) as f:
                f.write("@echo off\n")
                f.write(f'call "{export_script}" >nul 2>&1\n')
                f.write("if errorlevel 1 exit /b 1\n")
                f.write(f'python "{helper_path}"\n')
                wrapper_path = Path(f.name)

            result = subprocess.run(
                f'cmd /c "{wrapper_path}"',
                capture_output=True, text=True, timeout=180,
            )
        else:
            with tempfile.NamedTemporaryFile(
                suffix=".sh", delete=False, mode="w", encoding="utf-8"
            ) as f:
                f.write("#!/bin/bash\n")
                f.write(f'source "{export_script}" > /dev/null 2>&1\n')
                f.write(f'python3 "{helper_path}"\n')
                wrapper_path = Path(f.name)

            os.chmod(wrapper_path, 0o755)
            result = subprocess.run(
                ["/bin/bash", str(wrapper_path)],
                capture_output=True, text=True, timeout=180,
            )

        if result.returncode != 0:
            log_error(f"ESP-IDF export script failed (exit code {result.returncode})")
            if result.stderr:
                log_error(result.stderr.strip()[:500])
            sys.exit(1)

        if not env_json_path.exists() or env_json_path.stat().st_size == 0:
            log_error("Failed to capture ESP-IDF environment after export")
            sys.exit(1)

        with open(env_json_path, "r", encoding="utf-8") as f:
            new_env = json.load(f)
    finally:
        for p in [env_json_path, helper_path, wrapper_path]:
            if p and p.exists():
                p.unlink(missing_ok=True)

    # Apply environment changes
    changed = 0
    for key, value in new_env.items():
        if key not in old_env or old_env[key] != value:
            os.environ[key] = value
            changed += 1

    # Remove variables unset by export script
    for key in list(old_env.keys()):
        if key not in new_env:
            os.environ.pop(key, None)
            changed += 1

    log(f"ESP-IDF environment activated ({changed} env variable(s) updated)")


def _resolve_idf_py() -> List[str]:
    """Resolve the idf.py command as a list of arguments.

    Priority:
    1. ESP-IDF Python venv python + $IDF_PATH/tools/idf.py
    2. idf.py on system PATH
    3. python on PATH + $IDF_PATH/tools/idf.py
    4. sys.executable + $IDF_PATH/tools/idf.py (fallback)
    """
    idf_python_env = os.environ.get("_IDF_PYTHON_ENV", "")
    virtual_env = os.environ.get("VIRTUAL_ENV", "")
    idf_path = os.environ.get("IDF_PATH", "")

    # Check _IDF_PYTHON_ENV first, then VIRTUAL_ENV (set by export script)
    venv_candidate = idf_python_env or virtual_env
    if venv_candidate and idf_path:
        venv_dir = Path(venv_candidate)
        if sys.platform == "win32":
            python_exe = venv_dir / "Scripts" / "python.exe"
        else:
            python_exe = venv_dir / "bin" / "python"
        idf_py_script = Path(idf_path) / "tools" / "idf.py"

        if python_exe.exists() and idf_py_script.exists():
            return [str(python_exe), str(idf_py_script)]

    idf_on_path = find_tool("idf.py")
    if idf_on_path:
        return [idf_on_path]

    if idf_path:
        idf_py_script = Path(idf_path) / "tools" / "idf.py"
        if idf_py_script.exists():
            # Try Python on PATH first (may be ESP-IDF Python after export)
            python_name = "python.exe" if sys.platform == "win32" else "python3"
            python_on_path = find_tool(python_name)
            if python_on_path:
                return [python_on_path, str(idf_py_script)]
            return [sys.executable, str(idf_py_script)]

    log_error("idf.py not found. Configure idf_path and idf_python_env in config_workspace.json.")
    sys.exit(1)


def run_idf(
    workspace: Path,
    idf_args: List[str],
    verbose: bool = False,
) -> None:
    """Run an idf.py command in the given workspace."""
    idf_cmd = _resolve_idf_py() + idf_args
    log(f"$ {' '.join(idf_cmd)}")

    env = os.environ.copy()

    try:
        if verbose:
            subprocess.run(idf_cmd, cwd=str(workspace), check=True, text=True,
                            env=env)
        else:
            subprocess.run(idf_cmd, cwd=str(workspace), check=True,
                            capture_output=True, text=True, env=env)
    except subprocess.CalledProcessError as e:
        if not verbose:
            if e.stdout:
                print(e.stdout)
            if e.stderr:
                print(e.stderr, file=sys.stderr)
        log_error(f"idf.py {' '.join(idf_args)} failed (exit code {e.returncode})")
        sys.exit(e.returncode)


def find_tool(name: str) -> Optional[str]:
    """Find a tool on PATH."""
    return shutil.which(name)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


def load_config(config_path: Path, ci_mode: bool) -> Dict:
    """Load config_workspace.json, applying CI defaults if --ci."""
    if not config_path.exists():
        log_error(f"Config file not found: {config_path}")
        log_error("Create it or use --ci to auto-generate.")
        sys.exit(1)

    with open(config_path, encoding="utf-8") as f:
        config = json.load(f)

    required = ["toolname", "product_id", "idf_target", "build_type"]
    for field in required:
        if field not in config:
            log_error(f"Missing required field '{field}' in {config_path}")
            sys.exit(1)

    config.setdefault("buildno", "")
    config.setdefault("pre_test_firmware", False)
    config.setdefault("idf_path", "")
    config.setdefault("idf_python_env", "")
    config.setdefault("sdkconfig_overrides", {
        "common": {},
        "app_firmware": {},
        "app_bootloader": {},
    })

    if ci_mode and "ci_defaults" in config:
        ci = config["ci_defaults"]
        config["toolname"] = ci.get("toolname", config["toolname"])
        config["product_id"] = ci.get("product_id", config["product_id"])
        config["buildno"] = ci.get("buildno", config.get("buildno", ""))
        config["build_type"] = ci.get("build_type", config["build_type"])
        config["pre_test_firmware"] = ci.get(
            "pre_test_firmware", config.get("pre_test_firmware", False)
        )
        config["idf_path"] = ci.get("idf_path", config.get("idf_path", ""))
        config["idf_python_env"] = ci.get("idf_python_env", config.get("idf_python_env", ""))
        log(f"CI mode: applied ci_defaults (build_type={config['build_type']}, idf_path={config['idf_path']})")

    return config


def validate_config(config: Dict) -> None:
    """Validate config values."""
    if config["build_type"] not in ("dev", "release"):
        log_error(f"build_type must be 'dev' or 'release', got '{config['build_type']}'")
        sys.exit(1)

    if config["idf_target"] not in SUPPORTED_TARGETS:
        log_error(
            f"Unsupported idf_target '{config['idf_target']}'. "
            f"Supported: {', '.join(SUPPORTED_TARGETS)}"
        )
        sys.exit(1)


# ---------------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------------


def read_version() -> Tuple[str, str, str]:
    """Read VERSION file and return (major, minor, patch)."""
    if not VERSION_FILE.exists():
        log_error(f"VERSION file not found: {VERSION_FILE}")
        sys.exit(1)

    content = VERSION_FILE.read_text(encoding="utf-8").strip()
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)$", content)
    if not match:
        log_error(f"VERSION file must be XX.YY.ZZ format, got '{content}'")
        sys.exit(1)

    return match.group(1), match.group(2), match.group(3)


# ---------------------------------------------------------------------------
# sdkconfig overrides
# ---------------------------------------------------------------------------


def get_sdkconfig_overrides(
    config: Dict, workspace_key: str
) -> Dict[str, str]:
    """Merge common + workspace-specific sdkconfig overrides."""
    overrides = config.get("sdkconfig_overrides", {})
    merged = dict(overrides.get("common", {}))
    merged.update(overrides.get(workspace_key, {}))
    return merged


def write_sdkconfig_overrides(
    workspace: Path, overrides: Dict[str, str]
) -> Path:
    """Write sdkconfig.overrides file in the workspace directory."""
    overrides_path = workspace / "sdkconfig.overrides"
    lines = ["# Auto-generated by build.py — do not edit"]
    for key, value in sorted(overrides.items()):
        lines.append(f"{key}={value}")
    overrides_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    log(f"Written {overrides_path.relative_to(PROJECT_ROOT)} ({len(overrides)} overrides)")
    return overrides_path


def build_sdkconfig_defaults_chain(
    build_type: str, secure: bool, workspace_name: str
) -> str:
    """Build the SDKCONFIG_DEFAULTS chain string."""
    chain = ["sdkconfig.defaults"]
    if build_type == "dev":
        chain.append("sdkconfig.dev")
    elif build_type == "release":
        chain.append("sdkconfig.release")
    if secure and workspace_name == "app_bootloader":
        chain.append("sdkconfig.secure")
    chain.append("sdkconfig.overrides")
    return ";".join(chain)


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------


def build_workspace(
    workspace: Path,
    workspace_name: str,
    config: Dict,
    version: Tuple[str, str, str],
    args: argparse.Namespace,
) -> Dict[str, Path]:
    """Build a single workspace and return artifact paths."""
    verbose = args.verbose or args.ci
    major, minor, patch = version

    # --- sdkconfig overrides ---
    overrides = get_sdkconfig_overrides(
        config, "app_firmware" if workspace_name == "app_firmware" else "app_bootloader"
    )
    write_sdkconfig_overrides(workspace, overrides)

    # --- SDKCONFIG_DEFAULTS chain ---
    sdkconfig_chain = build_sdkconfig_defaults_chain(
        config["build_type"], args.secure, workspace_name
    )

    # --- CMake variables ---
    cmake_args = [
        f"-DPROJECT_TOOLNAME={config['toolname']}",
        f"-DPROJECT_PRODUCT_ID={config['product_id']}",
        f"-DFIRMWARE_BUILDNO={config['buildno']}",
        f"-DSDKCONFIG_DEFAULTS={sdkconfig_chain}",
    ]
    if config["pre_test_firmware"]:
        cmake_args.append("-DPRE_TEST_FIRMWARE=1")

    # --- Clean / reconfigure ---
    if args.clean:
        log(f"Cleaning {workspace_name}...")
        run_idf(workspace, ["fullclean"], verbose=verbose)

    # --- Set target ---
    log(f"Setting target {config['idf_target']} for {workspace_name}...")
    run_idf(workspace, ["set-target", config["idf_target"]], verbose=verbose)

    # --- Build ---
    log(f"Building {workspace_name}...")
    build_cmd = cmake_args + ["build"]
    if args.reconfigure:
        build_cmd = ["reconfigure"] + cmake_args + ["build"]
    run_idf(workspace, build_cmd, verbose=verbose)

    # --- Verify artifacts ---
    build_dir = workspace / "build"
    artifacts: Dict[str, Path] = {}
    expected_files = {
        "bootloader": build_dir / "bootloader" / "bootloader.bin",
        "partition_table": build_dir / "partition_table" / "partition-table.bin",
    }
    for name, path in expected_files.items():
        if not path.exists():
            log_error(f"Expected artifact not found: {path}")
            sys.exit(1)
        artifacts[name] = path

    # Find app binary (any .bin in build/ root that is not bootloader/partition-table)
    app_bins = [
        f
        for f in build_dir.glob("*.bin")
        if f.name not in ("bootloader.bin", "partition-table.bin")
    ]
    if not app_bins:
        log_error(f"No app binary found in {build_dir}")
        sys.exit(1)
    artifacts["app"] = app_bins[0]
    log(f"App binary: {artifacts['app'].name}")

    # Also check for .map and .elf
    map_files = list(build_dir.glob("*.map"))
    if map_files:
        artifacts["map"] = map_files[0]

    return artifacts


# ---------------------------------------------------------------------------
# Partition table parser
# ---------------------------------------------------------------------------


def parse_size(size_str: str) -> int:
    """Parse ESP-IDF size string (e.g. '1M', '512K', '0x10000') to bytes."""
    size_str = size_str.strip()
    if size_str.startswith("0x") or size_str.startswith("0X"):
        return int(size_str, 16)

    match = re.match(r"^(\d+(?:\.\d+)?)\s*([KMG]?)$", size_str, re.IGNORECASE)
    if not match:
        return int(size_str)

    value = float(match.group(1))
    unit = match.group(2).upper()

    multipliers = {"K": 1024, "M": 1024 * 1024, "G": 1024 * 1024 * 1024}
    multiplier = multipliers.get(unit, 1)
    return int(value * multiplier)


def parse_partition_table(csv_path: Path) -> List[Dict]:
    """Parse ESP-IDF partition table from CSV or binary.

    If a built partition-table.bin exists next to the CSV (in the build
    directory), its binary entries are used as the source of truth for offsets.
    Otherwise falls back to CSV parsing with sequential offset assignment.
    """
    partitions: List[Dict] = []

    # Try to read from built binary first (authoritative offsets)
    bin_path = WORKSPACE_BL / "build" / "partition_table" / "partition-table.bin"
    if bin_path.exists():
        return _parse_partition_table_binary(bin_path)

    # Fallback: parse CSV
    if not csv_path.exists():
        log_error(f"Partition table not found: {csv_path}")
        sys.exit(1)

    for line in csv_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        fields = [f.strip() for f in line.split(",")]
        if len(fields) < 5:
            continue

        name = fields[0]
        ptype = fields[1].lower()
        subtype = fields[2].lower()
        offset_str = fields[3].strip()
        size_str = fields[4].strip()
        flags = fields[5].strip() if len(fields) > 5 else ""

        offset = int(offset_str, 0) if offset_str else None
        size = parse_size(size_str)

        partitions.append({
            "name": name,
            "type": ptype,
            "subtype": subtype,
            "offset": offset,
            "size": size,
            "flags": flags,
        })

    # Assign offsets if not specified (ESP-IDF sequential layout)
    current_offset = 0
    for p in partitions:
        if p["offset"] is not None:
            current_offset = p["offset"]
        else:
            # Align to 4K boundary
            if current_offset % 4096 != 0:
                current_offset = ((current_offset // 4096) + 1) * 4096
            p["offset"] = current_offset
        current_offset += p["size"]

    return partitions


def _parse_partition_table_binary(bin_path: Path) -> List[Dict]:
    """Parse ESP-IDF partition table from binary format."""
    import struct

    data = bin_path.read_bytes()
    partitions: List[Dict] = []

    for i in range(len(data) // 32):
        entry = data[i * 32 : (i + 1) * 32]
        # ESP-IDF binary format: 2-byte magic (0xAA 0x50), then type, subtype
        magic = struct.unpack_from("<H", entry, 0)[0]
        if magic == 0xFFFF:
            break
        if magic != 0x50AA:
            continue

        ptype = entry[2]
        subtype = entry[3]
        offset = struct.unpack_from("<I", entry, 4)[0]
        size = struct.unpack_from("<I", entry, 8)[0]
        name = entry[12:28].split(b"\x00")[0].decode("utf-8", errors="replace")

        type_map = {0: "app", 1: "data"}
        subtype_map = {
            (0, 0x00): "factory",
            (0, 0x10): "ota_0",
            (0, 0x11): "ota_1",
            (1, 0x00): "ota",
            (1, 0x01): "phy",
            (1, 0x02): "nvs",
            (1, 0x04): "nvs_keys",
        }

        ptype_str = type_map.get(ptype, str(ptype))
        subtype_key = (ptype, subtype)
        subtype_str = subtype_map.get(subtype_key, str(subtype))

        partitions.append({
            "name": name,
            "type": ptype_str,
            "subtype": subtype_str,
            "offset": offset,
            "size": size,
            "flags": "",
        })

    log(f"Partition offsets from {bin_path.relative_to(PROJECT_ROOT)}")
    return partitions


# ---------------------------------------------------------------------------
# Merge
# ---------------------------------------------------------------------------


def read_flash_params(sdkconfig_path: Path) -> Tuple[str, str, str]:
    """Read flash parameters from sdkconfig.defaults."""
    flash_mode = "dio"
    flash_freq = "80m"
    flash_size = "16MB"

    if sdkconfig_path.exists():
        content = sdkconfig_path.read_text(encoding="utf-8")
        for line in content.splitlines():
            line = line.strip()
            if line.startswith("CONFIG_ESPTOOLPY_FLASHMODE="):
                flash_mode = line.split("=", 1)[1].strip('"')
            elif line.startswith("CONFIG_ESPTOOLPY_FLASHFREQ="):
                flash_freq = line.split("=", 1)[1].strip('"')
            elif line.startswith("CONFIG_ESPTOOLPY_FLASHSIZE="):
                flash_size = line.split("=", 1)[1].strip('"')

    return flash_mode, flash_freq, flash_size


def merge_binaries(
    bl_artifacts: Dict[str, Path],
    fw_artifacts: Dict[str, Path],
    partitions: List[Dict],
    config: Dict,
    output_dir: Path,
) -> Path:
    """Merge BL bootloader + partition + BL app + FW app into single binary."""
    esptool = find_tool("esptool.py") or find_tool("esptool")
    if not esptool:
        log_error("esptool not found. Ensure ESP-IDF is installed and on PATH.")
        sys.exit(1)

    flash_mode, flash_freq, flash_size = read_flash_params(
        WORKSPACE_BL / "sdkconfig.defaults"
    )

    # Find app partitions
    app_partitions = [p for p in partitions if p["type"] == "app"]
    if len(app_partitions) < 2:
        log_error(
            f"Expected at least 2 app partitions, found {len(app_partitions)}. "
            f"Partition table must have 'app_bootloader' and 'app_firmware'."
        )
        sys.exit(1)

    # Map partition names to binaries
    bl_partition = None
    fw_partition = None
    for p in app_partitions:
        if p["name"] == "app_bootloader" or p["subtype"] == "ota_0":
            bl_partition = p
        elif p["name"] == "app_firmware" or p["subtype"] == "ota_1":
            fw_partition = p

    if bl_partition is None:
        log_error("No 'app_bootloader' (ota_0) partition found in partition table.")
        sys.exit(1)
    if fw_partition is None:
        log_error("No 'app_firmware' (ota_1) partition found in partition table.")
        sys.exit(1)

    output_file = output_dir / "firmware_merged.bin"

    if "esptool.py" in (esptool or ""):
        cmd = [sys.executable, esptool]
    else:
        cmd = [esptool]
    cmd.extend([
        "--chip", config["idf_target"],
        "merge_bin",
        "--output", str(output_file),
        "--flash_mode", flash_mode,
        "--flash_freq", flash_freq,
        "--flash_size", flash_size,
        "0x0", str(bl_artifacts["bootloader"]),
        f"0x{PARTITION_TABLE_OFFSET:X}", str(bl_artifacts["partition_table"]),
        f"0x{bl_partition['offset']:X}", str(bl_artifacts["app"]),
        f"0x{fw_partition['offset']:X}", str(fw_artifacts["app"]),
    ])

    log(f"Merging binaries -> {output_file.name}")
    try:
        run_cmd(cmd, verbose=config.get("_verbose", False), check=True)
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        log_error(f"Merge failed: {e}")
        sys.exit(1)

    log(f"Merged binary: {output_file}")
    return output_file


# ---------------------------------------------------------------------------
# Release output
# ---------------------------------------------------------------------------


def copy_to_release(
    artifacts: Dict[str, Path],
    output_dir: Path,
    merged_bin: Optional[Path] = None,
) -> None:
    """Copy artifacts to release directory."""
    output_dir.mkdir(parents=True, exist_ok=True)

    for name, src in artifacts.items():
        if src.exists():
            dst = output_dir / src.name
            shutil.copy2(src, dst)
            log(f"  Copied {src.name} ({src.stat().st_size:,} bytes)")

    if merged_bin and merged_bin.exists():
        dst = output_dir / merged_bin.name
        if dst != merged_bin:
            shutil.copy2(merged_bin, dst)
        log(f"  Copied {merged_bin.name} ({merged_bin.stat().st_size:,} bytes)")


def generate_checksums(directory: Path) -> Path:
    """Generate SHA256 checksums for all .bin files in directory."""
    checksum_path = directory / "checksums.sha256"
    lines = []
    for f in sorted(directory.glob("*.bin")):
        sha = hashlib.sha256(f.read_bytes()).hexdigest()
        lines.append(f"{sha}  {f.name}")

    checksum_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    log(f"Generated {checksum_path.name}")
    return checksum_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build script for dtbao-IoT ESP-IDF projects",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--all", action="store_true", default=False,
                      help="Build firmware + bootloader then merge (default)")
    mode.add_argument("--fw", action="store_true", help="Build only firmware")
    mode.add_argument("--bl", action="store_true", help="Build only bootloader")

    parser.add_argument("--clean", action="store_true",
                        help="Full clean before build (idf.py fullclean)")
    parser.add_argument("--reconfigure", action="store_true",
                        help="Force reconfigure before build")
    parser.add_argument("--build-type", choices=["dev", "release"],
                        help="Override build_type from config")
    parser.add_argument("--secure", action="store_true",
                        help="Include sdkconfig.secure for bootloader build")
    parser.add_argument("--config", type=Path,
                        default=CONFIG_FILE,
                        help="Path to config_workspace.json")
    parser.add_argument("--ci", action="store_true",
                        help="CI mode: apply ci_defaults, verbose, non-interactive")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Verbose output")
    parser.add_argument("--output-dir", type=Path,
                        default=RELEASE_DIR,
                        help="Release output directory")

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    log("=" * 50)
    log("dtbao-IoT Build Script")
    log("=" * 50)

    # --- Read version ---
    version = read_version()
    log(f"Version: {version[0]}.{version[1]}.{version[2]}")

    # --- Load config ---
    config = load_config(args.config, args.ci)

    # --- Apply CLI overrides ---
    if args.build_type:
        config["build_type"] = args.build_type

    validate_config(config)
    config["_verbose"] = args.verbose or args.ci

    # --- Setup IDF environment ---
    setup_idf_env(config)

    log(f"Build type : {config['build_type']}")
    log(f"Target     : {config['idf_target']}")
    log(f"Toolname   : {config['toolname']}")
    log(f"Product ID : {config['product_id']}")

    # --- Check partition table ---
    if not PARTITIONS_CSV.exists():
        log_error(f"Partition table not found: {PARTITIONS_CSV}")
        log_error("Create configs_tool/partitions.csv before building.")
        sys.exit(1)

    # --- Default to --all if no mode specified ---
    if not args.all and not args.fw and not args.bl:
        args.all = True

    # --- Determine what to build ---
    build_fw = args.all or args.fw
    build_bl = args.all or args.bl

    # --- Output directory ---
    output_dir = args.output_dir / config["build_type"] / config["idf_target"]

    # --- Build ---
    fw_artifacts: Optional[Dict[str, Path]] = None
    bl_artifacts: Optional[Dict[str, Path]] = None

    if build_fw:
        log("-" * 40)
        log("Building firmware...")
        fw_artifacts = build_workspace(WORKSPACE_FW, "app_firmware", config, version, args)

    if build_bl:
        log("-" * 40)
        log("Building bootloader...")
        bl_artifacts = build_workspace(WORKSPACE_BL, "app_bootloader", config, version, args)

    # --- Merge ---
    merged_bin: Optional[Path] = None
    if args.all and fw_artifacts and bl_artifacts:
        log("-" * 40)
        log("Parsing partition table...")
        partitions = parse_partition_table(PARTITIONS_CSV)
        for p in partitions:
            log(f"  {p['name']:20s} 0x{p['offset']:06X} ({p['size']:>8d} bytes)  {p['type']}/{p['subtype']}")

        log("-" * 40)
        log("Merging binaries...")
        output_dir.mkdir(parents=True, exist_ok=True)
        merged_bin = merge_binaries(bl_artifacts, fw_artifacts, partitions, config, output_dir)

    # --- Copy to release ---
    log("-" * 40)
    log("Copying artifacts to release directory...")
    if build_fw:
        copy_to_release(fw_artifacts, output_dir, merged_bin if args.all else None)
    elif build_bl:
        copy_to_release(bl_artifacts, output_dir)

    # --- Generate checksums ---
    generate_checksums(output_dir)

    # --- Summary ---
    log("=" * 50)
    log("Build complete!")
    log(f"Output: {output_dir}")
    for f in sorted(output_dir.glob("*")):
        if f.is_file():
            log(f"  {f.name:40s} {f.stat().st_size:>10,} bytes")
    log("=" * 50)


if __name__ == "__main__":
    main()