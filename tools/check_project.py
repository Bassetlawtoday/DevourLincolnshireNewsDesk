"""
Devour Lincolnshire NewsDesk - Project Health Check

Compiles active Python files and reports useful project diagnostics.

Usage:
    py tools/check_project.py
"""

from datetime import datetime
from pathlib import Path
import platform
import py_compile
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parent.parent

EXCLUDED_DIRS = {
    "__pycache__",
    ".git",
    ".venv",
    "venv",
    ".pytest_cache",
}

BACKUP_MARKERS = (
    "_BACKUP",
    "_STABLE",
    "_WORKING",
    "_BROKEN",
)


def is_excluded(path: Path) -> bool:
    """Return True when a path is inside an excluded directory."""

    return any(part in EXCLUDED_DIRS for part in path.parts)


def is_backup_file(path: Path) -> bool:
    """Return True when a filename looks like a backup or archived version."""

    name = path.name.upper()
    return any(marker in name for marker in BACKUP_MARKERS)


def get_python_files():
    """Return active Python source files in the project."""

    for path in ROOT.rglob("*.py"):
        if not path.is_file():
            continue

        if is_excluded(path):
            continue

        if is_backup_file(path):
            continue

        yield path


def get_backup_files():
    """Return Python files identified as backups or stable snapshots."""

    for path in ROOT.rglob("*.py"):
        if not path.is_file():
            continue

        if is_excluded(path):
            continue

        if is_backup_file(path):
            yield path


def get_python_named_directories():
    """Return directories whose names incorrectly end with .py."""

    for path in ROOT.rglob("*"):
        if path.is_dir() and path.suffix.lower() == ".py":
            yield path


def compile_file(path: Path):
    """Compile one Python file and raise an exception on failure."""

    py_compile.compile(str(path), doraise=True)


def get_git_status():
    """Return Git status information without changing the repository."""

    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return "Unavailable", ["Git executable was not found."]

    if result.returncode != 0:
        message = result.stderr.strip() or "Git status command failed."
        return "Unavailable", [message]

    changes = [
        line
        for line in result.stdout.splitlines()
        if line.strip()
    ]

    if changes:
        return "Changes detected", changes

    return "Clean", []


def print_heading(title: str):
    """Print a consistent report section heading."""

    print()
    print(title)
    print("-" * 70)


def main():
    start = time.perf_counter()

    print("=" * 70)
    print("DEVOUR LINCOLNSHIRE NEWSDESK - PROJECT HEALTH CHECK")
    print("=" * 70)
    print(f"Started        : {datetime.now():%Y-%m-%d %H:%M:%S}")
    print(f"Python         : {platform.python_version()}")
    print(f"Platform       : {platform.system()} {platform.release()}")
    print(f"Project root   : {ROOT}")

    checked = 0
    failed = []

    print_heading("PYTHON COMPILATION")

    for file in sorted(get_python_files()):
        checked += 1
        relative_path = file.relative_to(ROOT)

        try:
            compile_file(file)
            print(f"✓ {relative_path}")

        except py_compile.PyCompileError as exc:
            print(f"✗ {relative_path}")
            print(f"  {exc.msg}")
            failed.append(relative_path)

        except Exception as exc:
            print(f"✗ {relative_path}")
            print(f"  {type(exc).__name__}: {exc}")
            failed.append(relative_path)

    backup_files = sorted(get_backup_files())

    print_heading("BACKUP FILE AUDIT")

    if backup_files:
        for file in backup_files:
            print(f"⚠ {file.relative_to(ROOT)}")
    else:
        print("✓ No backup-style Python files found")

    python_named_directories = sorted(get_python_named_directories())

    print_heading("PROJECT STRUCTURE AUDIT")

    if python_named_directories:
        for directory in python_named_directories:
            print(
                "⚠ Directory name ends with .py: "
                f"{directory.relative_to(ROOT)}"
            )
    else:
        print("✓ No directories incorrectly ending with .py")

    git_state, git_changes = get_git_status()

    print_heading("GIT STATUS")
    print(f"Git working tree: {git_state}")

    if git_changes:
        for change in git_changes:
            print(f"  {change}")

    elapsed = time.perf_counter() - start

    warning_count = (
        len(backup_files)
        + len(python_named_directories)
        + len(git_changes)
    )

    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Files compiled : {checked}")
    print(f"Syntax errors  : {len(failed)}")
    print(f"Warnings       : {warning_count}")
    print(f"Backup files   : {len(backup_files)}")
    print(f"Git            : {git_state}")
    print(f"Time taken     : {elapsed:.2f} seconds")

    if failed:
        print("Result         : FAIL")
        print("=" * 70)
        sys.exit(1)

    print("Result         : PASS")
    print("=" * 70)


if __name__ == "__main__":
    main()