#!/usr/bin/env python3
"""Build the file scope and review prompt for the simplify skill."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

STATUS_MAP = {
    "M": "modified",
    "A": "added",
    "R": "renamed",
    "C": "copied",
}


@dataclass(frozen=True)
class LineRange:
    start: int
    end: int


@dataclass(frozen=True)
class ChangedFile:
    path: str
    status: str
    changed_lines: tuple[LineRange, ...] | None = None


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Print the simplify review scope and prompt.",
    )
    parser.add_argument(
        "--staged",
        action="store_true",
        help="Inspect only staged changes.",
    )
    parser.add_argument(
        "--ref",
        default="HEAD",
        help="Git ref to diff against when --staged is not set.",
    )
    parser.add_argument(
        "--cwd",
        default=".",
        help="Repository directory. Defaults to the current directory.",
    )
    parser.add_argument(
        "files",
        nargs="*",
        help="Explicit files to review.",
    )
    return parser.parse_args(argv)


def run_git(cwd: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=False,
        text=True,
        capture_output=True,
    )


def parse_diff_output(stdout: str) -> list[ChangedFile]:
    files: list[ChangedFile] = []
    for line in stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        status_code = parts[0][0] if parts and parts[0] else ""
        status = STATUS_MAP.get(status_code)
        if not status:
            continue
        path_index = 2 if status in {"renamed", "copied"} else 1
        if len(parts) > path_index and parts[path_index]:
            files.append(ChangedFile(path=parts[path_index], status=status))
    return files


def parse_changed_lines(stdout: str) -> tuple[LineRange, ...]:
    ranges: list[LineRange] = []
    pattern = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")

    for line in stdout.splitlines():
        match = pattern.match(line)
        if not match:
            continue

        start = int(match.group(1))
        count = 1 if match.group(2) is None else int(match.group(2))
        if count == 0:
            continue

        end = start + count - 1
        if ranges and start <= ranges[-1].end + 1:
            previous = ranges[-1]
            ranges[-1] = LineRange(previous.start, max(previous.end, end))
        else:
            ranges.append(LineRange(start, end))

    return tuple(ranges)


def diff_args(staged: bool, ref: str, path: str) -> list[str]:
    args = ["diff", "--unified=0", "--no-ext-diff"]
    if staged and ref != "HEAD~1":
        args.append("--cached")
    else:
        args.append(ref)
    args.extend(["--", path])
    return args


def add_changed_lines(
    cwd: Path,
    staged: bool,
    files: list[ChangedFile],
    ref: str,
) -> list[ChangedFile]:
    scoped_files: list[ChangedFile] = []
    for file in files:
        if file.status == "added":
            scoped_files.append(file)
            continue

        result = run_git(cwd, diff_args(staged, ref, file.path))
        changed_lines = (
            parse_changed_lines(result.stdout) if result.returncode == 0 else None
        )
        scoped_files.append(ChangedFile(file.path, file.status, changed_lines))

    return scoped_files


def get_changed_files(
    cwd: Path, staged: bool, ref: str, files: list[str]
) -> list[ChangedFile]:
    if files:
        explicit_files = [ChangedFile(path=file, status="modified") for file in files]
        return add_changed_lines(cwd, staged, explicit_files, ref)

    args = ["diff", "--name-status"]
    if staged:
        args.append("--cached")
    else:
        args.append(ref)

    result = run_git(cwd, args)
    if result.returncode == 0:
        changed = parse_diff_output(result.stdout)
        if changed:
            return add_changed_lines(cwd, staged, changed, ref)

    fallback = run_git(cwd, ["diff", "--name-status", "HEAD~1"])
    if fallback.returncode == 0:
        changed = parse_diff_output(fallback.stdout)
        return add_changed_lines(cwd, staged, changed, "HEAD~1")

    return []


def format_file(file: ChangedFile) -> str:
    if file.status == "added":
        return f"- {file.path} (added; entire file is in scope)"
    if file.changed_lines is None:
        return (
            f"- {file.path} ({file.status}; changed lines unavailable — "
            "inspect git diff before editing)"
        )
    if not file.changed_lines:
        return f"- {file.path} ({file.status}; deletions only — no current lines to simplify)"

    ranges = ", ".join(
        str(line_range.start)
        if line_range.start == line_range.end
        else f"{line_range.start}-{line_range.end}"
        for line_range in file.changed_lines
    )
    return f"- {file.path} ({file.status}; changed lines: {ranges})"


def build_prompt(files: list[ChangedFile]) -> str:
    file_list = "\n".join(format_file(file) for file in files)
    return f"""Review the following recently changed files and apply simplification improvements.

## Principles

- **Preserve functionality**: Never change what the code does. All existing tests must continue to pass.
- **Apply project standards**: Follow any conventions from CLAUDE.md or AGENTS.md in this project.
- **Enhance clarity**: Reduce unnecessary complexity and nesting, eliminate redundant code and abstractions, improve variable and function names, and consolidate related logic. Keep valuable comments that explain design rationale, business rules, non-obvious behaviour, or intent. Remove only truly redundant noise, such as `// increment i` above `i++`. Avoid nested ternary operators: prefer switch statements or if/else chains for multiple conditions.
- **Maintain balance**: Do not over-simplify. Avoid overly clever solutions that are hard to understand. Do not combine too many concerns into single functions. Do not remove helpful abstractions. Prioritize readability over fewer lines.

## Scope

Only review and modify the changed lines listed below. Changed line numbers refer to
the current file contents. You may read surrounding code for context, but must not
edit it. For added files, the entire file is considered changed.
{file_list}

## Process

1. Read each file listed above and inspect its changed lines
2. Identify concrete improvements within those lines (dead code, unclear names, redundant logic, inconsistent patterns)
3. Apply changes one file at a time, keeping every edit within the listed line ranges
4. After all changes, run existing tests to verify nothing is broken
5. Summarize what you changed and why

Do NOT add new features, change public APIs, or refactor code outside the listed
line ranges. If a worthwhile simplification would require editing unchanged code,
leave it alone and mention it in the summary instead."""


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    cwd = Path(args.cwd).expanduser().resolve()
    changed_files = get_changed_files(cwd, args.staged, args.ref, args.files)

    if not changed_files:
        print("No changed files found. Specify file paths or make some changes first.")
        return 1

    print(build_prompt(changed_files))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
