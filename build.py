#!/usr/bin/env python3

import argparse
import datetime
import getpass
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent
DIAGNOSTIC_DIR = ROOT / "diagnostic"
DIAGNOSTIC_CHUNK_SIZE = 40 * 1024 * 1024
ENCRYPTLY_BLOCKER_MESSAGE = "You need to fix your environment so encryptly runs before building."


def current_commit_id() -> str:
    """Return the first 4 bytes (8 hex chars) of HEAD for stable per-commit diagnostics."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=5,
        )
        commit = result.stdout.strip()
        if result.returncode == 0 and len(commit) >= 8:
            return commit[:8]
    except Exception:
        pass
    return "00000000"


def diagnostic_paths_for_commit() -> tuple[Path, Path, str]:
    """Return stable diagnostic artifact paths under diagnostic/ for the current commit."""
    DIAGNOSTIC_DIR.mkdir(parents=True, exist_ok=True)
    commit_id = current_commit_id()
    logd_path = DIAGNOSTIC_DIR / f"build-{commit_id}.logd"
    metadata_path = DIAGNOSTIC_DIR / f"build-{commit_id}.json"
    return logd_path, metadata_path, commit_id


def split_diagnostic_logd(logd_path: Path, chunk_size: int = DIAGNOSTIC_CHUNK_SIZE) -> list[Path]:
    """Split an oversized .logd into numbered .logd chunks and remove the original."""
    if logd_path.stat().st_size <= chunk_size:
        return [logd_path]

    chunks: list[Path] = []
    stem = logd_path.stem
    with logd_path.open("rb") as source:
        index = 1
        while True:
            data = source.read(chunk_size)
            if not data:
                break
            chunk_path = logd_path.with_name(f"{stem}-part{index:03d}.logd")
            chunk_path.write_bytes(data)
            chunks.append(chunk_path)
            index += 1

    logd_path.unlink()
    return chunks


def clean_module(module_path: Path, commands: list[list[str]]) -> list[str]:
    """Run clean commands for a module and return a list of failed command descriptions."""
    failed_commands: list[str] = []
    for cmd in commands:
        try:
            result = subprocess.run(
                cmd,
                cwd=str(module_path),
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode != 0:
                cmd_str = " ".join(cmd)
                failed_commands.append(f"{module_path.name}: {cmd_str} (exit {result.returncode})")
        except subprocess.TimeoutExpired:
            cmd_str = " ".join(cmd)
            failed_commands.append(f"{module_path.name}: {cmd_str} (timeout)")
        except Exception as e:
            cmd_str = " ".join(cmd)
            failed_commands.append(f"{module_path.name}: {cmd_str} ({e})")
    return failed_commands


def clean_all() -> int:
    """Clean all build artifacts from all modules."""
    all_failed: list[str] = []

    # Clean Gradle modules
    gradle_modules = [
        ROOT / "android",
    ]
    for module in gradle_modules:
        if module.exists():
            all_failed.extend(clean_module(module, [["./gradlew", "clean"]]))

    # Clean Cargo modules
    cargo_modules = [
        ROOT / "core",
    ]
    for module in cargo_modules:
        if module.exists():
            all_failed.extend(clean_module(module, [["cargo", "clean"]]))

    # Clean diagnostic directory
    if DIAGNOSTIC_DIR.exists():
        try:
            shutil.rmtree(DIAGNOSTIC_DIR)
        except Exception as e:
            all_failed.append(f"diagnostic: rmtree ({e})")

    if all_failed:
        print("Clean completed with errors:")
        for failure in all_failed:
            print(f"  - {failure}")
        return 1
    else:
        print("Clean completed successfully.")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="ZeroEye build script")
    parser.add_argument("--clean", action="store_true", help="Clean all build artifacts")
    args = parser.parse_args()

    if args.clean:
        return clean_all()

    print("Build not yet implemented.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
