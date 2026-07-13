---
name: simplify
description: Simplify recently changed code while preserving behavior and limiting edits to Git-diff line ranges. Use when the user asks to simplify, clean up, improve readability, reduce complexity, remove redundancy, or run a /simplify-style pass. Supports --staged, --ref=REF, and explicit file paths.
---

# Simplify Changed Code

## Invocation

When the user invokes this skill, parse optional arguments from the user text:

- `--staged`: inspect only staged changes.
- `--ref=<ref>`: diff against the given git ref. Default is `HEAD`.
- Any other tokens that look like file paths: restrict the review to those paths.

For every invocation, resolve `scripts/simplify_scope.py` relative to this
`SKILL.md` and run it with the parsed arguments. Do not assume a particular home
directory or skill installation root. Run it from the target repository root, or
pass `--cwd <repo>` when operating on a different repository.

The helper intentionally mirrors the upstream scope behavior:

- It uses Git diffs, so untracked files are excluded from the scope.
- If the selected diff has no eligible files, it falls back to `HEAD~1`.
- Deleted files are excluded. Added files are reviewed in full; other files are
  limited to their changed lines in the current contents.

If the helper reports no changed files, relay that result and stop. Otherwise,
follow its generated review prompt exactly. Read surrounding code only for
context, and keep every edit within the reported line ranges.
