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


def run_text_process(cmd: list[str], cwd: Optional[str] = None) -> subprocess.CompletedProcess:
    """Run a subprocess and return the completed process."""
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def clean_module(module_name: str, clean_cmd: list[str], cwd: Optional[str] = None, verbose: bool = False) -> bool:
    """
    Run a module's clean command and report success/failure.

    Args:
        module_name: Name of the module being cleaned
        clean_cmd: Command list to execute
        cwd: Working directory for the command
        verbose: If True, print output even on success

    Returns:
        True if clean succeeded, False otherwise
    """
    try:
        result = run_text_process(clean_cmd, cwd=cwd)
    except FileNotFoundError as e:
        print(f"[FAIL] {module_name}: Command not found: {e}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"[FAIL] {module_name}: Unexpected error: {e}", file=sys.stderr)
        return False

    if result.returncode != 0:
        print(f"[FAIL] {module_name}: Clean command exited with code {result.returncode}", file=sys.stderr)
        if result.stdout:
            print(f"Stdout:\n{result.stdout}", file=sys.stderr)
        if result.stderr:
            print(f"Stderr:\n{result.stderr}", file=sys.stderr)
        return False

    if verbose:
        print(f"[OK] {module_name}: Clean successful")
        if result.stdout:
            print(result.stdout)

    return True
