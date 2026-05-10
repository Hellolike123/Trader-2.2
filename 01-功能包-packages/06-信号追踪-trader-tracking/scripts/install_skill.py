#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path


def _hermes_root() -> Path:
    home = Path.home()
    if home.name == ".hermes":
        return home / "skills"
    return home / ".hermes" / "skills"


PRESET_ROOTS = {
    "codex": Path.home() / ".agents" / "skills",
    "hermes": _hermes_root(),
    "openclaw": Path.home() / ".openclaw" / "workspace" / "skills",
}


def load_skill_name(src: Path) -> str:
    meta_path = src / "_meta.json"
    if meta_path.exists():
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        name = str(data.get("name") or "").strip()
        if name:
            return name
    skill_path = src / "SKILL.md"
    for line in skill_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("name:"):
            return line.split(":", 1)[1].strip().strip('"\'')
    raise RuntimeError("cannot determine skill name from _meta.json or SKILL.md")


def default_target(preset: str, skill_name: str) -> Path:
    return PRESET_ROOTS[preset] / skill_name


def main() -> int:
    parser = argparse.ArgumentParser(description="Install this Trader skill package.")
    parser.add_argument("--preset", choices=sorted(PRESET_ROOTS), default="codex")
    parser.add_argument("--target")
    parser.add_argument("--allow-name-mismatch", action="store_true")
    args = parser.parse_args()

    src = Path(__file__).resolve().parents[1]
    skill_name = load_skill_name(src)
    dest = Path(args.target).expanduser() if args.target else default_target(args.preset, skill_name)
    if dest.name != skill_name and not args.allow_name_mismatch:
        print(
            f"INSTALL_REFUSED=name mismatch: package {skill_name!r} cannot install to {str(dest)!r}. "
            f"Use --target .../{skill_name} or pass --allow-name-mismatch explicitly.",
            file=sys.stderr,
        )
        return 2

    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "*.pyc", ".DS_Store"))
    copied_name = load_skill_name(dest)
    if copied_name != skill_name:
        print(f"INSTALL_FAILED=installed metadata changed from {skill_name!r} to {copied_name!r}", file=sys.stderr)
        return 3
    print(f"SKILL_NAME={skill_name}")
    print(f"INSTALLED_TO={dest}")
    print(f"PRESET={args.preset}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
