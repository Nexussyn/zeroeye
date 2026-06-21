#!/usr/bin/env python3
"""Build and clean utilities for ZeroEye modules."""

import subprocess
import sys
from typing import Optional


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
