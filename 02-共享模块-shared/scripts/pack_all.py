#!/usr/bin/env python3
"""Pack all skills into correctly structured zips for Hermes/Agent installation.

Produces archives in 03-安装包-dist/<timestamp>/:
   - Individual skill zips (trader.zip, t0-trader.zip, etc.)
     Files at root of zip, no prefix
   - Combined archives: live-trader.zip & review-commander.zip (super-skills)
   - Combined archive (trader-all-skill.zip)
     Files under <skill_name>/ prefix, unzip into ~/.hermes/skills/

Run from anywhere in the repo:
    python3 02-共享模块-shared/scripts/pack_all.py
"""
from __future__ import annotations

import json
import hashlib
import os
import shutil
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

# Active skills
SKILLS = [
    ("01-单票分析-trader", "trader"),
    ("02-盘中T0-t0-trader", "t0-trader"),
    ("03-选股池-trader-pool", "trader-pool"),
    ("04-仓位轮动-trader-portfolio", "trader-portfolio"),
    ("05-盘后复盘-review-trader", "review-trader"),
    ("06-信号追踪-trader-tracking", "trader-tracking"),
]

IGNORE_NAMES = {"__pycache__", ".pytest_cache", ".DS_Store"}
SHARE_DIR = Path("02-共享模块-shared")
MAX_RELEASES = 5


def compute_file_sha256(p: Path) -> str:
    """Return hex SHA-256 of a file."""
    h = hashlib.sha256()
    try:
        h.update(p.read_bytes())
    except OSError:
        return "0" * 64
    return h.hexdigest()


def shared_files_for_skill(staged_root: Path) -> dict[str, str]:
    shares: dict[str, str] = {}
    scripts = staged_root / "scripts"

    for f in ("signal_contract.py", "signal_store.py", "signal_utils.py"):
        p = scripts / f
        if p.exists() and p.stat().st_size > 0:
            shares[f"contracts/{f}"] = compute_file_sha256(p)

    for f in ("pipeline.py", "signal_tracker.py", "market_env.py", "calibrator.py"):
        p = scripts / f
        if p.exists() and p.stat().st_size > 0:
            shares[f"scripts/{f}"] = compute_file_sha256(p)

    p = scripts / "light_data.py"
    if p.exists() and p.stat().st_size > 0:
        shares["market-data/light_data.py"] = compute_file_sha256(p)

    return shares


def concat_digest(shares: dict[str, str]) -> str:
    joined = "|".join(sorted(shares.values()))
    return hashlib.sha256(joined.encode()).hexdigest()[:16]


def read_version_stamp(skill_dir: Path, skill_slug: str) -> str:
    stamp = skill_dir / "VERSION_STAMP"
    if not stamp.exists():
        return "unversioned"
    text = stamp.read_text(encoding="utf-8").strip()
    if not text:
        return "unversioned"
    prefix = f"{skill_slug}:"
    if text.startswith(prefix):
        text = text[len(prefix):].strip()
    return text.replace(" ", "_")


def build_release_dir_name() -> str:
    now = datetime.now()
    return now.strftime("%m%d-%H%M")


def parse_release_date(name: str) -> datetime | None:
    try:
        parts = name.split("-")
        if len(parts) != 2:
            return None
        md, time_part = parts
        if len(md) != 4:
            return None
        month = int(md[:2])
        day = int(md[2:])
        hour = int(time_part[:2])
        minute = int(time_part[2:4])
        return datetime(2020, month, day, hour, minute)
    except Exception:
        return None


def days_between(anchor: datetime, target: datetime) -> float:
    diff = anchor - target
    if diff.days < -300:
        adjusted_target = datetime(target.year - 1, target.month, target.day, target.hour, target.minute)
        return (anchor - adjusted_target).total_seconds() / 86400.0
    return diff.total_seconds() / 86400.0


def cleanup_old_releases(releases_dir: Path, keep: int = MAX_RELEASES) -> int:
    if not releases_dir.exists() or keep <= 0:
        return 0
    dirs = [d for d in releases_dir.iterdir() if d.is_dir() and d.name != ".gitkeep"]
    if not dirs:
        return 0
    parsed_dirs: list[tuple[Path, datetime]] = []
    for d in dirs:
        dt = parse_release_date(d.name)
        if dt is not None:
            parsed_dirs.append((d, dt))
    if not parsed_dirs:
        return 0
    parsed_dirs.sort(key=lambda item: item[1])
    _, anchor_dt = parsed_dirs[-1]
    removed_count = 0
    for path, dt in parsed_dirs:
        diff_days = days_between(anchor_dt, dt)
        if diff_days > keep:
            shutil.rmtree(path, ignore_errors=True)
            removed_count += 1
    return removed_count


def ensure_releases_gitignore(releases_dir: Path) -> None:
    releases_dir.mkdir(parents=True, exist_ok=True)
    gitignore = releases_dir / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text("# Release archives — auto-generated, do not track\n*\n!.gitignore\n", encoding="utf-8")


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
    scripts_dir = bundle / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)

    contracts_dir = SHARE_DIR / "03-输出校验-contracts"
    for f in ("signal_contract.py", "signal_store.py", "signal_utils.py"):
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
    for f in ("chan_core.py", "wyckoff_core.py", "momentum_core.py",
              "fusion_core.py", "fusion_regime.py",
              "time_window_detector.py"):
        src = candidates_dir / f
        if src.exists():
            shutil.copy2(src, scripts_dir / f)

    if "t0" in skill_slug or "live" in skill_slug:
        core = candidates_dir / "t0_candidate_core.py"
        if core.exists():
            shutil.copy2(core, scripts_dir / "candidate_core.py")
        for extra in ("structure_core.py", "decision_core.py"):
            src = candidates_dir / extra
            if src.exists():
                shutil.copy2(src, scripts_dir / extra)
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
    tmp = Path(tempfile.mkdtemp(prefix=f"trader-{skill_slug}-"))
    staged = tmp / skill_slug
    shutil.copytree(
        skill_dir, staged,
        ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "*.pyc", ".DS_Store"),
    )
    copy_shared(staged, skill_slug)
    return staged


def add_to_zip(staged: Path, archive: zipfile.ZipFile, arc_prefix: str = "") -> None:
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


def auto_install(stages: list[tuple[str, str, Path]]) -> None:
    hermes_dir = Path.home() / ".hermes" / "skills"
    hermes_dir.mkdir(parents=True, exist_ok=True)
    print("\n--- Auto-install ---")
    for skill_slug, version, staged in stages:
        dest = hermes_dir / skill_slug
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(staged, dest)
        meta_path = dest / "_meta.json"
        if meta_path.exists():
            meta_name = json.loads(meta_path.read_text(encoding="utf-8")).get("name", skill_slug)
        else:
            meta_name = skill_slug
        print(f"  {meta_name} -> {dest}")


def main(args: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Pack traderskills into zips")
    parser.add_argument("--no-install", action="store_true", help="Skip auto-install to ~/.hermes/skills/")
    parsed, _ = parser.parse_known_args(args if args is not None else None)

    if os.environ.get("PACK_NO_INSTALL") or "pytest" in sys.modules:
        parsed.no_install = True

    root = repo_root()
    packages_dir = root / "01-功能包-packages"
    output_dir = root / "03-安装包-dist"
    release_dir_name = build_release_dir_name()
    release_dir = output_dir / "releases" / release_dir_name
    output_dir.mkdir(parents=True, exist_ok=True)
    release_dir.mkdir(parents=True, exist_ok=True)
    ensure_releases_gitignore(output_dir / "releases")
    removed = cleanup_old_releases(output_dir / "releases")
    if removed:
        print(f"Cleaned up {removed} old release(s), keeping {MAX_RELEASES} latest")
    print(f"Release dir: {release_dir_name}/")

    stages: list[tuple[str, str, Path]] = []

    # 1. Pack individual skills (for backward compatibility)
    for dir_name, skill_slug in SKILLS:
        src = packages_dir / dir_name
        if not src.exists():
            print(f"SKIP: {src} not found", file=sys.stderr)
            continue
        version = read_version_stamp(src, skill_slug)
        print(f"Stage: {dir_name} -> {skill_slug} ({version})")
        staged = stage_skill(src, skill_slug)
        stages.append((skill_slug, version, staged))

    # 2. Pack live-trader (Super-skill for active trading)
    print("\nStage Combined Super-Skill: live-trader")
    tmp_live = Path(tempfile.mkdtemp(prefix="trader-live-trader-"))
    staged_live = tmp_live / "live-trader"
    staged_live.mkdir(parents=True, exist_ok=True)
    for d in ("01-单票分析-trader", "02-盘中T0-t0-trader"):
        src_path = packages_dir / d
        if src_path.exists():
            for item in src_path.iterdir():
                if item.name in IGNORE_NAMES or item.suffix == ".pyc":
                    continue
                dst_item = staged_live / item.name
                if item.is_dir():
                    if dst_item.exists():
                        # Merge directory
                        for sub_item in item.rglob("*"):
                            if should_skip(sub_item):
                                continue
                            rel_sub = sub_item.relative_to(item)
                            sub_dst = dst_item / rel_sub
                            sub_dst.parent.mkdir(parents=True, exist_ok=True)
                            if not sub_item.is_dir():
                                shutil.copy2(sub_item, sub_dst)
                    else:
                        shutil.copytree(item, dst_item, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "*.pyc", ".DS_Store"))
                else:
                    shutil.copy2(item, dst_item)

    # Overwrite _meta.json and SKILL.md for live-trader
    meta_live = {
        "name": "live-trader",
        "version": "1.0.0-unified-live",
        "contract": "live_trader_v1",
        "description": "Script-output skill. Unified live trading commander. Use scripts/run_trader.py live --target <股票名或代码> to run full stock diagnostic, or scripts/run_trader.py live --monitor to run active watch alert, or scripts/run_trader.py live --show to show live ladder snapshot of pool items. Return stdout verbatim. Never handwrite, summarize, restyle, translate, or append follow-up lines."
    }
    (staged_live / "_meta.json").write_text(json.dumps(meta_live, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    
    skill_live_md = """---
name: live-trader
description: Unified live trading commander for diagnostic & watch alert.
version: 1.0.0-unified-live
author: Trader Central
license: MIT
platforms: [macos, linux]
tags: [finance, stocks, live, terminal, python]
metadata:
  hermes:
    tags: [Finance, AShare, Live, Terminal]
    requires_toolsets: [terminal]
dependencies: [python3]
repository: local
documentation: SKILL.md
---

# Live Trader (盘中现场)

Unified live trading commander. MUST run scripts/run_trader.py live and return stdout verbatim.

## Commands
  - Diagnostic: `python3 scripts/run_trader.py live --target <股票名>`
  - T0 Monitor: `python3 scripts/run_trader.py live --monitor`
  - Show Ladder: `python3 scripts/run_trader.py live --show`
"""
    (staged_live / "SKILL.md").write_text(skill_live_md, encoding="utf-8")
    copy_shared(staged_live, "live-trader")
    stages.append(("live-trader", "1.0.0-unified-live", staged_live))

    # 3. Pack review-commander (Super-skill for post-market commander)
    print("Stage Combined Super-Skill: review-commander")
    tmp_review = Path(tempfile.mkdtemp(prefix="trader-review-commander-"))
    staged_review = tmp_review / "review-commander"
    staged_review.mkdir(parents=True, exist_ok=True)
    for d in ("03-选股池-trader-pool", "04-仓位轮动-trader-portfolio", "05-盘后复盘-review-trader", "06-信号追踪-trader-tracking"):
        src_path = packages_dir / d
        if src_path.exists():
            for item in src_path.iterdir():
                if item.name in IGNORE_NAMES or item.suffix == ".pyc":
                    continue
                dst_item = staged_review / item.name
                if item.is_dir():
                    if dst_item.exists():
                        for sub_item in item.rglob("*"):
                            if should_skip(sub_item):
                                continue
                            rel_sub = sub_item.relative_to(item)
                            sub_dst = dst_item / rel_sub
                            sub_dst.parent.mkdir(parents=True, exist_ok=True)
                            if not sub_item.is_dir():
                                shutil.copy2(sub_item, sub_dst)
                    else:
                        shutil.copytree(item, dst_item, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "*.pyc", ".DS_Store"))
                else:
                    shutil.copy2(item, dst_item)

    # Overwrite _meta.json and SKILL.md for review-commander
    meta_review = {
        "name": "review-commander",
        "version": "1.0.0-unified-review",
        "contract": "review_commander_v1",
        "description": "Script-output skill. Unified post-market commander. Use scripts/run_trader.py review --all to run end-to-end full review of all pool and holding stocks, which returns sorted priorities, golden fib bids, big order validation, signal tracker verifications, and portfolio cash guidance. Return stdout verbatim. Never handwrite, summarize, restyle, translate, or append follow-up lines."
    }
    (staged_review / "_meta.json").write_text(json.dumps(meta_review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    
    skill_review_md = """---
name: review-commander
description: Unified post-market commander for pool management & automated full review.
version: 1.0.0-unified-review
author: Trader Central
license: MIT
platforms: [macos, linux]
tags: [finance, stocks, review, terminal, python]
metadata:
  hermes:
    tags: [Finance, AShare, Review, Terminal]
    requires_toolsets: [terminal]
dependencies: [python3]
repository: local
documentation: SKILL.md
---

# Review Commander (盘后指挥官)

Unified post-market commander. MUST run scripts/run_trader.py review and return stdout verbatim.

## Commands
  - One-click All: `python3 scripts/run_trader.py review --all`
  - Single Review: `python3 scripts/run_trader.py review --target <股票名>`
"""
    (staged_review / "SKILL.md").write_text(skill_review_md, encoding="utf-8")
    copy_shared(staged_review, "review-commander")
    stages.append(("review-commander", "1.0.0-unified-review", staged_review))

    # --- Compute shared bundle digest ---
    bundle_digests: dict[str, str] = {}
    for skill_slug, _, staged in stages:
        shares = shared_files_for_skill(staged)
        dig = concat_digest(shares)
        bundle_digests[skill_slug] = dig

    # --- Update _meta.json with bundle digest ---
    for skill_slug, _, staged in stages:
        meta_path = staged / "_meta.json"
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            meta["shared_bundle"] = bundle_digests.get(skill_slug, "unknown")
            meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # --- Build individual zips ---
    print("\n--- Packing archives ---")
    for skill_slug, version, staged in stages:
        zip_name = f"{skill_slug}.zip"
        zip_path = release_dir / zip_name
        if zip_path.exists():
            zip_path.unlink()
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            add_to_zip(staged, archive, arc_prefix="")
        print(f"  -> {zip_path.relative_to(output_dir)}  ({zip_path.stat().st_size / 1024:.0f} KB)")

    # --- Combined zip (skill_name/ prefix) ---
    all_name = "trader-all-skill.zip"
    all_path = release_dir / all_name
    if all_path.exists():
        all_path.unlink()
    with zipfile.ZipFile(all_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for skill_slug, _, staged in stages:
            add_to_zip(staged, archive, arc_prefix=skill_slug)
    print(f"\nCombined: {all_path.relative_to(output_dir)}  ({all_path.stat().st_size / 1024:.0f} KB)")

    if parsed.no_install:
        print("\n[no-install] skipped auto-install")
    else:
        auto_install(stages)

    # --- Verify ---
    print("\n--- Verification ---")
    for skill_slug, _, _ in stages:
        zip_path = release_dir / f"{skill_slug}.zip"
        with zipfile.ZipFile(zip_path, "r") as archive:
            names = archive.namelist()
            has_meta = "_meta.json" in names
            has_scripts = any(n.startswith("scripts/") for n in names)
            has_hermes = "HERMES.md" in names
            has_skill = "SKILL.md" in names
            empty_py = [n for n in names if n.endswith(".py") and archive.getinfo(n).file_size == 0]
            empty_status = "EMPTY!" if empty_py else ""
            
            meta_digest = "unknown"
            if "_meta.json" in names:
                try:
                    meta = json.loads(archive.read("_meta.json").decode("utf-8"))
                    meta_digest = meta.get("shared_bundle", "unknown")
                except Exception:
                    meta_digest = "bad_meta"
            
            status = "ok" if has_meta and has_scripts and has_hermes and has_skill and empty_status != "EMPTY!" else "MISSING"
            print(f"  [{status}] {zip_path.name}  meta={has_meta} scripts={has_scripts} hermes={has_hermes} skill={has_skill} digest={meta_digest[:8]} {empty_status}")

    # Cleanup temp dirs
    for _, _, staged in stages:
        shutil.rmtree(staged.parent, ignore_errors=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
