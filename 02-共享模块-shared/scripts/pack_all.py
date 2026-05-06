#!/usr/bin/env python3
"""Pack all skills into correctly structured zips for Hermes/Agent installation.

Produces two types of archives in 03-安装包-dist/:
  - Individual skill zips (trader.zip, t0-trader.zip, etc.)
    → Files at root level, unzip directly into ~/.hermes/skills/<skill>/
  - Combined archive (trader-all-skill.zip)
    → Files under <skill_name>/ prefix, unzip into ~/.hermes/skills/

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
    ("01-单票分析-trader", "trader"),
    ("02-盘中T0-t0-trader", "t0-trader"),
    ("03-选股池-trader-pool", "trader-pool"),
    ("04-仓位轮动-trader-portfolio", "trader-portfolio"),
    ("05-盘后复盘-review-trader", "review-trader"),
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


def copy_shared(bundle: Path, skill_slug: str) -> None:
    """Copy shared modules into each skill bundle."""
    scripts_dir = bundle / "scripts"

    contracts_dir = SHARE_DIR / "03-输出校验-contracts"
    for f in ("signal_contract.py", "signal_store.py"):
        src = contracts_dir / f
        if src.exists():
            shutil.copy2(src, scripts_dir / f)

    shared_scripts_dir = SHARE_DIR / "scripts"
    for f in ("pipeline.py", "signal_tracker.py", "market_env.py", "calibrator.py"):
        src = shared_scripts_dir / f
        if src.exists():
            shutil.copy2(src, scripts_dir / f)

    src = SHARE_DIR / "01-行情数据-market-data" / "light_data.py"
    if src.exists():
        shutil.copy2(src, scripts_dir / "light_data.py")

    src = SHARE_DIR / "contract_utils.py"
    if src.exists():
        shutil.copy2(src, scripts_dir / "contract_utils.py")

    candidates_dir = SHARE_DIR / "02-候选逻辑-candidate"
    # Theory modules needed by all skills
    for f in ("chan_core.py", "wyckoff_core.py", "momentum_core.py"):
        src = candidates_dir / f
        if src.exists():
            shutil.copy2(src, scripts_dir / f)

    if "t0" in skill_slug:
        core = candidates_dir / "t0_candidate_core.py"
        if core.exists():
            shutil.copy2(core, scripts_dir / "candidate_core.py")
    else:
        for src_name, dst_name in (
            ("candidate_core.py", "candidate_core.py"),
            ("structure_core.py", "structure_core.py"),
            ("decision_core.py", "decision_core.py"),
        ):
            src = candidates_dir / src_name
            if src.exists():
                shutil.copy2(src, scripts_dir / dst_name)

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


def stage_skill(skill_dir: Path, skill_slug: str) -> Path:
    """Copy skill + shared into a temp directory. Returns staged root."""
    tmp = Path(tempfile.mkdtemp(prefix=f"trader-{skill_slug}-"))
    staged = tmp / skill_slug
    shutil.copytree(
        skill_dir, staged,
        ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "*.pyc", ".DS_Store"),
    )
    copy_shared(staged, skill_slug)
    return staged


def add_to_zip(staged: Path, archive: zipfile.ZipFile, arc_prefix: str = "") -> None:
    """Add files from staged dir to archive with optional arc_prefix.

    If arc_prefix is empty, files are at root of zip.
    If arc_prefix is 'trader', files are under 'trader/' in the zip.
    """
    for p in sorted(staged.rglob("*")):
        if should_skip(p):
            continue
        rel = p.relative_to(staged)
        if arc_prefix:
            arc_name = f"{arc_prefix}/{rel.as_posix()}"
        else:
            arc_name = rel.as_posix()
        if p.is_dir():
            archive.write(p, f"{arc_name}/")
        else:
            archive.write(p, arc_name)


def main() -> int:
    root = repo_root()
    packages_dir = root / "01-功能包-packages"
    output_dir = root / "03-安装包-dist"
    output_dir.mkdir(exist_ok=True)

    stages: list[tuple[str, Path]] = []

    for dir_name, skill_slug in SKILLS:
        src = packages_dir / dir_name
        if not src.exists():
            print(f"SKIP: {src} not found", file=sys.stderr)
            continue
        print(f"Stage: {dir_name} → {skill_slug}")
        staged = stage_skill(src, skill_slug)
        stages.append((skill_slug, staged))

    # --- Individual zips (flat, no prefix) ---
    for skill_slug, staged in stages:
        zip_path = output_dir / f"{skill_slug}.zip"
        if zip_path.exists():
            zip_path.unlink()
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            add_to_zip(staged, archive, arc_prefix="")
        print(f"  → {zip_path.name}  ({zip_path.stat().st_size / 1024:.0f} KB)")

    # --- Combined zip (skill_name/ prefix) ---
    all_path = output_dir / "trader-all-skill.zip"
    if all_path.exists():
        all_path.unlink()
    with zipfile.ZipFile(all_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for skill_slug, staged in stages:
            add_to_zip(staged, archive, arc_prefix=skill_slug)
    print(f"\nCombined: {all_path.name}  ({all_path.stat().st_size / 1024:.0f} KB)")

    # --- Verify ---
    print("\n--- Verification ---")
    for skill_slug, _ in stages:
        zip_path = output_dir / f"{skill_slug}.zip"
        with zipfile.ZipFile(zip_path, "r") as archive:
            names = archive.namelist()
            has_meta = "_meta.json" in names
            has_scripts = any(n.startswith("scripts/") for n in names)
            has_hermes = "HERMES.md" in names
            has_skill = "SKILL.md" in names
            status = "✅" if has_meta and has_scripts and has_hermes and has_skill else "❌"
            print(f"  {status} {skill_slug}.zip  meta={has_meta} scripts={has_scripts} hermes={has_hermes} skill={has_skill}")

    # Cleanup temp dirs
    for _, staged in stages:
        shutil.rmtree(staged.parent)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
