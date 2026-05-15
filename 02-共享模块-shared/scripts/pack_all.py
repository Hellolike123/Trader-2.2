#!/usr/bin/env python3
"""Pack all skills into correctly structured zips for Hermes/Agent installation.

Produces archives in 03-安装包-dist/<timestamp>/:
   - Individual skill zips (trader.zip, t0-trader.zip, etc.)
     Files at root of zip, no prefix
   - Combined archive (trader-all-skill.zip)
     Files under <skill_name>/ prefix, unzip into ~/.hermes/skills/

Run from anywhere in the repo:
    python3 02-共享模块-shared/scripts/pack_all.py

After packing, this script auto-installs all skills into ~/.hermes/skills/
so they are immediately available when you send the zip to Hermes.
"""
from __future__ import annotations

import json
import hashlib
import os
import shutil
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

# Active skills (deprecated trader-compare removed)
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
MAX_RELEASES = 5  # 最多保留最近 N 个发布目录


# ============================================================
# Shared module version consistency
# ============================================================
# When pack_all.py copies shared modules into each skill bundle,
# it computes SHA256 hashes of every shared file.  The concatenation
# of all those hashes (sorted by path) forms a *bundle digest* that
# is written into _meta.json  as "shared_bundle".
#
# After packing, the verification step reads _meta.json from each
# zip and verifies that:
#   1. shared_bundle is present
#   2. all skills that share the same subset get the SAME digest
#   3. no shared file is empty (0 bytes)
#
# This catches "shared file was stale / empty / old copy" silently.


def compute_file_sha256(p: Path) -> str:
    """Return hex SHA-256 of a file."""
    h = hashlib.sha256()
    try:
        h.update(p.read_bytes())
    except OSError:
        return "0" * 64
    return h.hexdigest()


def shared_files_for_skill(staged_root: Path) -> dict[str, str]:
    """Map of shared file paths → SHA256 for every shared file in the staged bundle.

    Reads from the staged bundle location to capture what's actually being packed.
    """
    shares: dict[str, str] = {}
    scripts = staged_root / "scripts"

    # contracts dir (signal_contract.py, signal_store.py, signal_utils.py)
    for f in ("signal_contract.py", "signal_store.py", "signal_utils.py"):
        p = scripts / f
        if p.exists() and p.stat().st_size > 0:
            shares[f"contracts/{f}"] = compute_file_sha256(p)

    # scripts dir (pipeline, signal_tracker, market_env, calibrator)
    for f in ("pipeline.py", "signal_tracker.py", "market_env.py", "calibrator.py"):
        p = scripts / f
        if p.exists() and p.stat().st_size > 0:
            shares[f"scripts/{f}"] = compute_file_sha256(p)

    # light_data
    p = scripts / "light_data.py"
    if p.exists() and p.stat().st_size > 0:
        shares["market-data/light_data.py"] = compute_file_sha256(p)

    return shares


def concat_digest(shares: dict[str, str]) -> str:
    """Hash the sorted values to form a single bundle digest."""
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
    """本地时间命名：0514-1105"""
    now = datetime.now()
    return now.strftime("%m%d-%H%M")


def cleanup_old_releases(releases_dir: Path, keep: int = MAX_RELEASES) -> int:
    """Remove old release directories, keeping the last one per day.

    1. Per-day dedup: for each day, only the latest release is kept;
       earlier same-day releases are always removed.
    2. From the deduped list, keep the most recent ``keep`` entries;
       older days are pruned.

    Returns the number of directories removed.
    """
    if not releases_dir.exists() or keep <= 0:
        return 0
    dirs = sorted(
        [d for d in releases_dir.iterdir() if d.is_dir() and d.name != ".gitkeep"],
        key=lambda d: d.name,
    )
    # Group by day prefix (MMDD) — keep only the last entry per day
    by_day: dict[str, list[Path]] = {}
    for d in dirs:
        day = d.name.split("-")[0]  # e.g. "0514"
        by_day.setdefault(day, []).append(d)

    # Step 1: last release per day (already in chronological order)
    last_per_day = [day_dirs[-1] for day_dirs in by_day.values()]

    # Step 2: from deduped list, keep only the most recent `keep`
    to_keep = set(last_per_day[-keep:]) if keep < len(last_per_day) else set(last_per_day)

    # Step 3: remove everything not in to_keep
    to_remove = [d for d in dirs if d not in to_keep]
    for d in to_remove:
        shutil.rmtree(d, ignore_errors=True)
    return len(to_remove)


def ensure_releases_gitignore(releases_dir: Path) -> None:
    """Create .gitignore in releases dir so release zips are not tracked by git."""
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
    """Copy shared modules into each skill bundle."""
    scripts_dir = bundle / "scripts"

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
    # Theory modules needed by all skills
    for f in ("chan_core.py", "wyckoff_core.py", "momentum_core.py",
              "fusion_core.py", "fusion_regime.py",
              "time_window_detector.py"):
        src = candidates_dir / f
        if src.exists():
            shutil.copy2(src, scripts_dir / f)

    if "t0" in skill_slug:
        core = candidates_dir / "t0_candidate_core.py"
        if core.exists():
            shutil.copy2(core, scripts_dir / "candidate_core.py")
        # C-11 fix: T0 也需要 structure_core.py（T0-1 修复后 find_key_levels 依赖 structure_result 的字段）
        # 和 decision_core.py（t0_candidate_core 依赖 decision_core 的 status_for/score_for）
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


def auto_install(stages: list[tuple[str, str, Path]]) -> None:
    """After packing, auto-install all skills into ~/.hermes/skills/."""
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

    # Also skip auto-install when running under pytest (prevents test pollution)
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

    for dir_name, skill_slug in SKILLS:
        src = packages_dir / dir_name
        if not src.exists():
            print(f"SKIP: {src} not found", file=sys.stderr)
            continue
        version = read_version_stamp(src, skill_slug)
        print(f"Stage: {dir_name} -> {skill_slug} ({version})")
        staged = stage_skill(src, skill_slug)
        stages.append((skill_slug, version, staged))

    # --- Compute shared bundle digest ---
    # All stages should produce the same digest if shared modules are identical.
    # If they differ, it means copy_shared had a conditional (e.g. t0 vs non-t0)
    # and we need to compare by skill subset.
    bundle_digests: dict[str, str] = {}
    for skill_slug, _, staged in stages:
        shares = shared_files_for_skill(staged)
        dig = concat_digest(shares)
        bundle_digests[skill_slug] = dig

    # Find which skill uses the largest set of shared files (the "base" set)
    # All others should be a subset of this base set.
    all_digests = set(bundle_digests.values())
    if len(all_digests) == 1:
        # All stages share the same files — single digest for everyone
        _SHARED_BUNDLE_DIGEST = all_digests.pop()
    else:
        # Different skill subsets have different files (e.g. t0 gets extra modules)
        # We still record a digest per skill so downstream can compare.
        _SHARED_BUNDLE_DIGEST = None

    print(f"\nShared bundle digest: {_SHARED_BUNDLE_DIGEST or '(multi-subset)'}")

    # --- Update _meta.json with bundle digest ---
    for skill_slug, _, staged in stages:
        meta_path = staged / "_meta.json"
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            meta["shared_bundle"] = bundle_digests.get(skill_slug, "unknown")
            meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # --- Build individual zips ---
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
    digests_in_zips: dict[str, str] = {}
    for skill_slug, _, _ in stages:
        zip_path = release_dir / f"{skill_slug}.zip"
        with zipfile.ZipFile(zip_path, "r") as archive:
            names = archive.namelist()
            has_meta = "_meta.json" in names
            has_scripts = any(n.startswith("scripts/") for n in names)
            has_hermes = "HERMES.md" in names
            has_skill = "SKILL.md" in names
            # Check for empty .py files — indicates stale/incomplete copy
            empty_py = [n for n in names if n.endswith(".py") and archive.getinfo(n).file_size == 0]
            empty_status = "EMPTY!" if empty_py else ""
            
            # Read bundle digest from _meta.json inside zip
            meta_digest = "unknown"
            if "_meta.json" in names:
                try:
                    meta = json.loads(archive.read("_meta.json").decode("utf-8"))
                    meta_digest = meta.get("shared_bundle", "unknown")
                except Exception:
                    meta_digest = "bad_meta"
            
            digests_in_zips[skill_slug] = meta_digest
            
            # Check digest consistency: all non-t0 skills must match, t0 = its own subset
            status = "ok" if has_meta and has_scripts and has_hermes and has_skill and empty_status != "EMPTY!" else "MISSING"
            print(f"  [{status}] {zip_path.name}  meta={has_meta} scripts={has_scripts} hermes={has_hermes} skill={has_skill} digest={meta_digest[:8]} {empty_status}")
            if empty_py:
                print(f"         EMPTY files: {', '.join(empty_py)}")
            if meta_digest == "bad_meta":
                print(f"         BAD _meta.json")
    # Cross-check digests consistency
    non_none = [d for d in digests_in_zips.values() if d != "unknown" and d is not None]
    unique_digests = set(non_none)
    if len(unique_digests) == 1:
        print(f"  ✓ All {len(non_none)} skills share same bundle digest {list(unique_digests)[0][:8]}")
    elif len(unique_digests) > 1:
        # Some skills share extra files (e.g. t0-trader has structure_core, decision_core)
        for sk, d in sorted(digests_in_zips.items()):
            if d == "unknown" or d is None:
                continue
            match_mark = "↔" if d == list(unique_digests)[0] else "⚡"
            print(f"    {match_mark} {sk}: {d[:8]}")

    # Cleanup temp dirs
    for _, _, staged in stages:
        shutil.rmtree(staged.parent)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
