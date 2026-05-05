#!/usr/bin/env python3
"""Unified installer packer — one zip for all skills.

Produces a single archive (trader-all-skill.zip) containing all active skills
with their directories preserved.  Any agent platform (Hermes, OpenClaw,
Work Buddy) can extract & symlink from this one file.

Run from anywhere in the repo:
    python3 02-共享模块-shared/scripts/pack_all.py
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

# Active skills (deprecated trader-compare removed)
SKILLS = [
    "01-单票分析-trader",
    "02-盘中T0-t0-trader",
    "03-选股池-trader-pool",
    "04-仓位轮动-trader-portfolio",
    "05-盘后复盘-review-trader",
]

IGNORE_NAMES = {"__pycache__", ".pytest_cache", ".DS_Store"}
SHARE_DIR = Path("02-共享模块-shared")


def should_skip(path: Path) -> bool:
    return any(part in IGNORE_NAMES for part in path.parts) or path.suffix == ".pyc"


def repo_root() -> Path:
    root = Path(__file__).resolve().parents[2]
    if (root / ".git").exists():
        return root
    for p in root.parents:
        if (p / ".git").exists():
            return p
    return root


def copy_shared(bundle: Path, skill_name: str) -> None:
    """Copy shared modules into each skill bundle."""
    scripts_dir = bundle / "scripts"

    # shared contracts
    contracts_dir = SHARE_DIR / "03-输出校验-contracts"
    for f in ("signal_contract.py", "signal_store.py"):
        src = contracts_dir / f
        if src.exists():
            shutil.copy2(src, scripts_dir / f)

    # shared runtime scripts required by trader_shared dynamic loader
    shared_scripts_dir = SHARE_DIR / "scripts"
    for f in ("pipeline.py", "signal_tracker.py", "market_env.py", "calibrator.py"):
        src = shared_scripts_dir / f
        if src.exists():
            shutil.copy2(src, scripts_dir / f)

    # shared light_data
    src = SHARE_DIR / "01-行情数据-market-data" / "light_data.py"
    if src.exists():
        shutil.copy2(src, scripts_dir / "light_data.py")

    # shared contract_utils
    src = SHARE_DIR / "contract_utils.py"
    if src.exists():
        shutil.copy2(src, scripts_dir / "contract_utils.py")

    # candidate logic — differs per skill
    candidates_dir = SHARE_DIR / "02-候选逻辑-candidate"
    if "t0" in skill_name:
        core = candidates_dir / "t0_candidate_core.py"
        if core.exists():
            shutil.copy2(core, scripts_dir / "candidate_core.py")
    else:
        # candidate_core is now a thin compatibility shell that imports
        # structure_core / decision_core, so all three must be shipped.
        for src_name, dst_name in (
            ("candidate_core.py", "candidate_core.py"),
            ("structure_core.py", "structure_core.py"),
            ("decision_core.py", "decision_core.py"),
        ):
            src = candidates_dir / src_name
            if src.exists():
                shutil.copy2(src, scripts_dir / dst_name)

    # embed trader_shared package for self-contained runtime
    shared_pkg_src = SHARE_DIR / "trader_shared"
    shared_pkg_dst = scripts_dir / "trader_shared"
    if shared_pkg_src.exists():
        if shared_pkg_dst.exists():
            shutil.rmtree(shared_pkg_dst)
        shutil.copytree(
            shared_pkg_src,
            shared_pkg_dst,
            ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "*.pyc", ".DS_Store"),
        )


def pack_skill(skill_dir: Path, skill_name: str, archive: zipfile.ZipFile) -> None:
    """Stage a single skill and add it to the archive."""
    with tempfile.TemporaryDirectory(prefix=f"trader-{skill_name}-") as tmp:
        staged = Path(tmp) / skill_name
        shutil.copytree(
            skill_dir, staged,
            ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "*.pyc", ".DS_Store"),
        )
        copy_shared(staged, skill_name)
        for p in sorted(staged.rglob("*")):
            if should_skip(p):
                continue
            rel = p.relative_to(staged)
            # Keep original repository package prefix so remote agents (e.g. Hermes)
            # can locate skills by documented path: 01-功能包-packages/<skill>/...
            arc_name = f"01-功能包-packages/{skill_name}/{rel.as_posix()}"
            if p.is_dir():
                archive.write(p, f"{arc_name}/")
            else:
                archive.write(p, arc_name)


def main() -> int:
    import shutil
    root = repo_root()
    packages_dir = root / "01-功能包-packages"
    output_dir = root / "03-安装包-dist"
    output_dir.mkdir(exist_ok=True)

    archive_path = output_dir / "trader-all-skill.zip"
    # Remove old archive so zip starts fresh
    if archive_path.exists():
        archive_path.unlink()

    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for skill_name in SKILLS:
            src = packages_dir / skill_name
            if not src.exists():
                print(f"SKIP: {src} not found", file=sys.stderr)
                continue
            print(f"Pack: {skill_name}")
            pack_skill(src, skill_name, archive)

    print(f"\nGenerated: {archive_path}")
    print(f"Size: {archive_path.stat().st_size / 1024:.0f} KB")

    # List contents summary
    with zipfile.ZipFile(archive_path, "r") as archive:
        skill_dirs = sorted(set(n.split("/")[0] for n in archive.namelist() if "/" in n and n[:-1] != n))
        print(f"Skills: {', '.join(skill_dirs)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
