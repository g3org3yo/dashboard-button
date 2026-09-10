#!/usr/bin/env python3
"""Hermes desktop plugin-SDK hotfix.

Fixes the desktop-app bug that makes EVERY on-disk plugin fail to load in
production builds with:

    [plugins] runtime load failed (<id>) TypeError: Cannot convert undefined or
    null to object (.../dist/assets/sdk-<hash>.js:5)

Cause: the app's `src/sdk/runtime.ts` captures the plugin-SDK namespaces in a
MODULE-SCOPE object literal, in a module that sits in an import cycle. In a
bundled build the SDK namespace is a hoisted `var` assigned AFTER that literal,
so the captured value is `undefined` and the first `Object.keys(...)` throws.
The throw happens in `loadRuntimePlugin()` *before* a plugin's own code runs, so
no plugin can work around it — the app bundle has to be fixed.

This script rewrites the shipped bundle so those four properties are lazy
getters (read at call time, when the namespaces exist). Same fix as upstream
PR NousResearch/hermes-agent#107303, applied in place to an installed app.

Upstream: https://github.com/NousResearch/hermes-agent/issues/107304

Usage:
    python hermes-plugin-sdk-hotfix.py                 # report only (dry run)
    python hermes-plugin-sdk-hotfix.py --apply         # patch + verify
    python hermes-plugin-sdk-hotfix.py --root /path    # search one extra root
    python hermes-plugin-sdk-hotfix.py --check-only    # force report-only

After patching: fully restart the Hermes desktop app (close it and reopen it),
then open Capabilities -> Plugins and confirm the plugin row no longer says
`failed`.

Exit codes: 0 = nothing to do / patched ok, 1 = affected file found but not
patched (dry run), 2 = error.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

MARKER = "__HERMES_PLUGIN_SDK__"

# The buggy shape, minified-name agnostic: the four properties as DATA
# properties, in the emitted order. The first three values are plain minified
# identifiers; the jsx-dev one is whatever expression the bundler produced
# (usually `e(At(),1)`), so it may contain commas and parens but no braces —
# `[^{}]+` stops exactly at the literal's closing brace.
BUGGY = re.compile(
    r"\{__HERMES_PLUGIN_SDK__:(?P<sdk>[^,{}]+),"
    r"__HERMES_REACT__:(?P<react>[^,{}]+),"
    r"__HERMES_REACT_JSX__:(?P<jsx>[^,{}]+),"
    r"__HERMES_REACT_JSX_DEV__:(?P<dev>[^{}]+)\}"
)

FIXED_MARK = "get __HERMES_PLUGIN_SDK__(){"

SKIP_DIRS = {
    ".git",
    ".venv",
    "Cache",
    "Code Cache",
    "GPUCache",
    "DawnGraphiteCache",
    "DawnWebGPUCache",
    "__pycache__",
    "node_modules",
    "venv",
}


def replacement(match: re.Match[str]) -> str:
    return (
        "{"
        "get __HERMES_PLUGIN_SDK__(){return " + match.group("sdk") + "},"
        "get __HERMES_REACT__(){return " + match.group("react") + "},"
        "get __HERMES_REACT_JSX__(){return " + match.group("jsx") + "},"
        "get __HERMES_REACT_JSX_DEV__(){return " + match.group("dev") + "}"
        "}"
    )


def default_roots() -> list[Path]:
    home = Path.home()
    roots: list[Path] = [home / "hermes-agent" / "apps" / "desktop" / "release"]

    if sys.platform == "win32":
        local = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
        roots += [
            local / "hermes" / "hermes-agent" / "apps" / "desktop" / "release",
            local / "hermes" / "apps" / "desktop" / "release",
            local / "Programs",
        ]
    elif sys.platform == "darwin":
        roots += [Path("/Applications"), home / "Applications"]
    else:
        roots += [
            home / "hermes-agent" / "apps" / "desktop" / "release",
            Path("/opt"),
            Path("/usr/local/lib"),
        ]

    return roots


def find_bundles(roots: list[Path], max_depth: int = 12) -> list[Path]:
    """Bundles that mention the plugin SDK, newest first."""
    found: dict[Path, float] = {}
    for root in roots:
        if not root.exists():
            continue
        base_depth = len(root.parts)
        for dirpath, dirnames, filenames in os.walk(root):
            here = Path(dirpath)
            if len(here.parts) - base_depth >= max_depth:
                dirnames[:] = []
                continue
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for name in filenames:
                if not (name.startswith("sdk-") and name.endswith(".js")):
                    continue
                path = here / name
                try:
                    if path.stat().st_size > 8_000_000:
                        continue
                    if MARKER in path.read_text(encoding="utf-8", errors="ignore"):
                        found[path] = path.stat().st_mtime
                except OSError:
                    continue
    return sorted(found, key=lambda p: found[p], reverse=True)


def node_syntax_ok(path: Path) -> bool | None:
    """True/False when node is available, None when it is not."""
    if shutil.which("node") is None:
        return None
    try:
        proc = subprocess.run(
            ["node", "--check", str(path)], capture_output=True, text=True, timeout=60
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.returncode == 0


def patch(path: Path, apply: bool) -> str:
    """Return a one-line verdict for this bundle."""
    try:
        source = path.read_text(encoding="utf-8")
    except OSError as exc:
        return f"ERROR  cannot read: {exc}"

    if FIXED_MARK in source:
        return "OK     already fixed"

    matches = list(BUGGY.finditer(source))
    if not matches:
        return "SKIP   no matching globals literal (different build layout)"

    if len(matches) > 1:
        return f"SKIP   {len(matches)} matches — refusing to guess"

    if not apply:
        return "AFFECTED  would patch (re-run with --apply)"

    backup = path.with_name(path.name + ".bak-hermes-hotfix")
    if not backup.exists():
        shutil.copy2(path, backup)

    patched = BUGGY.sub(replacement, source, count=1)
    tmp = path.with_name(path.name + ".hermes-hotfix.tmp")
    tmp.write_text(patched, encoding="utf-8", newline="")
    os.replace(tmp, path)

    verify = path.read_text(encoding="utf-8")
    problems = []
    if FIXED_MARK not in verify:
        problems.append("marker missing after write")
    if BUGGY.search(verify):
        problems.append("buggy literal still present")
    syntax = node_syntax_ok(path)
    if syntax is False:
        problems.append("node --check failed")

    if problems:
        shutil.copy2(backup, path)
        return "ERROR  " + "; ".join(problems) + " (restored from backup)"

    return f"PATCHED  backup: {backup.name}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write the fix (default is a report-only dry run)",
    )
    parser.add_argument(
        "--check-only", action="store_true", help="never write, even with --apply"
    )
    parser.add_argument(
        "--root",
        action="append",
        default=[],
        metavar="DIR",
        help="extra root to search (repeatable)",
    )
    args = parser.parse_args()

    apply = args.apply and not args.check_only

    roots = [Path(r).expanduser() for r in args.root] + default_roots()
    bundles = find_bundles(roots)

    print("Hermes desktop plugin-SDK hotfix")
    print(f"mode: {'APPLY' if apply else 'REPORT ONLY (dry run)'}")
    print(f"searched: {', '.join(str(r) for r in roots if r.exists()) or '(no roots found)'}")

    if not bundles:
        print("\nNo desktop renderer bundle found.")
        print("If Hermes Desktop is installed somewhere else, point at it directly:")
        print("  python hermes-plugin-sdk-hotfix.py --root <install-dir> --apply")
        return 2

    print(f"\n{len(bundles)} bundle(s) mentioning the plugin SDK:\n")
    affected = 0
    for path in bundles:
        verdict = patch(path, apply)
        print(f"  [{verdict.split()[0]}] {path}")
        print(f"           {verdict}")
        if verdict.startswith("AFFECTED"):
            affected += 1

    if apply:
        print("\nDone. Fully RESTART the Hermes desktop app (close + reopen),")
        print("then check Capabilities -> Plugins: the plugin row must not say `failed`.")
        return 0

    if affected:
        print(f"\n{affected} affected bundle(s). Re-run with --apply to fix them,")
        print("then restart the Hermes desktop app.")
        return 1

    print("\nNothing to do — no affected bundle found.")
    print("(If your plugin still shows `failed`, the app may ship a packed")
    print(" app.asar without the unpacked assets; update Hermes once the upstream")
    print(" fix lands: https://github.com/NousResearch/hermes-agent/issues/107304)")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(2)
