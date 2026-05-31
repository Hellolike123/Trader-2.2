#!/usr/bin/env python3
"""Pack A-Share Trader into exactly ONE single consolidated super-skill zip.

Produces archives in 03-安装包-dist/<timestamp>/:
   - trader.zip (The ONLY unified A-Share Trader Commander skill)

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

    for f in ("pipeline.py", "signal_tracker.py", "market_env.py", "calibrator.py"):
        p = scripts / f
        if p.exists() and p.stat().st_size > 0:
            shares[f"scripts/{f}"] = compute_file_sha256(p)

    # Digest from trader_shared package (contains all migrated modules)
    trader_shared_dir = scripts / "trader_shared"
    if trader_shared_dir.exists():
        for f in sorted(trader_shared_dir.glob("*.py")):
            if f.name == "__init__.py":
                continue
            if f.stat().st_size > 0:
                shares[f"trader_shared/{f.name}"] = compute_file_sha256(f)

    return shares


def concat_digest(shares: dict[str, str]) -> str:
    joined = "|".join(sorted(shares.values()))
    return hashlib.sha256(joined.encode()).hexdigest()[:16]


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

    # Copy scripts that haven't moved into trader_shared yet
    shared_scripts_dir = SHARE_DIR / "scripts"
    for f in ("pipeline.py", "signal_tracker.py", "market_env.py", "calibrator.py"):
        src = shared_scripts_dir / f
        if src.exists():
            shutil.copy2(src, scripts_dir / f)

    src = SHARE_DIR / "contract_utils.py"
    if src.exists():
        shutil.copy2(src, scripts_dir / "contract_utils.py")

    # Copy the entire trader_shared package (contains all migrated modules)
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

    # Generate re-export stubs for bare imports
    # Scripts do `from light_data import ...` but code is in `trader_shared/light_data.py`
    # Stubs bridge the gap so both repo and packaged environments work
    _STUB_MODULES = [
        "light_data", "config", "signal_contract", "signal_store", "signal_utils",
        "models", "candidate_core", "chan_core", "wyckoff_core", "momentum_core",
        "decision_core", "structure_core", "fusion_core", "fusion_regime",
        "hmm_regime", "bayesian_fusion", "volume_profile", "order_book",
        "t0_candidate_core", "time_window_detector", "stage_positioning",
        "chip_distribution", "big_order", "extend_data", "data_provider",
        "cache_utils", "modifier_rule_engine", "rule_engine", "strategy_protocol",
        "data_manager", "self_check_agg",
    ]
    for mod_name in _STUB_MODULES:
        stub_path = scripts_dir / f"{mod_name}.py"
        if not stub_path.exists():
            stub_path.write_text(
                f'"""Re-export stub — {mod_name} has moved to trader_shared.{mod_name}."""\n'
                f'from trader_shared.{mod_name} import *  # noqa: F401,F403\n',
                encoding="utf-8",
            )


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
    backup_dir = hermes_dir / ".backup"
    
    # Clean up all obsolete directories to guarantee a single-skill workspace
    for old_skill in ("trader-pool", "trader-portfolio", "review-trader", "trader-tracking", 
                      "t0-trader", "live-trader", "review-commander"):
        dest = hermes_dir / old_skill
        if dest.exists():
            shutil.rmtree(dest)
            
    print("\n--- Auto-install (ONE Unified Super-Skill) ---")
    for skill_slug, version, staged in stages:
        dest = hermes_dir / skill_slug
        if dest.exists():
            # Backup existing skill before overwriting
            backup_dir.mkdir(parents=True, exist_ok=True)
            backup_dest = backup_dir / f"{skill_slug}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            shutil.copytree(dest, backup_dest)
            print(f"  [backup] {skill_slug} -> {backup_dest}")
            shutil.rmtree(dest)
        shutil.copytree(staged, dest)
        meta_path = dest / "_meta.json"
        if meta_path.exists():
            meta_name = json.loads(meta_path.read_text(encoding="utf-8")).get("name", skill_slug)
        else:
            meta_name = skill_slug
        print(f"  [The Only Super-Skill] {meta_name} -> {dest}")


def main(args: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Pack trader into exactly ONE single super-skill zip")
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

    # Stage the 3 skills: trader, t0, review
    skills_to_pack = ["trader", "t0", "review"]

    for skill_name in skills_to_pack:
        print(f"\nStage skill: {skill_name}")
        tmp_dir = Path(tempfile.mkdtemp(prefix=f"{skill_name}-"))
        staged = tmp_dir / skill_name
        staged.mkdir(parents=True, exist_ok=True)

        src_path = packages_dir / skill_name
        if src_path.exists():
            for item in src_path.iterdir():
                if item.name in IGNORE_NAMES or item.suffix == ".pyc":
                    continue
                dst_item = staged / item.name
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

        # Copy shared modules into each skill
        copy_shared(staged, skill_name)
        stages.append((skill_name, "2.4.0", staged))

    # Copy extra files to trader
    if stages:
        trader_staged = stages[0][2]
        _EXTRA_FILES = {
            root / "scripts" / "t0_cron.py": "scripts/t0_cron.py",
        }
        for _src, _rel in _EXTRA_FILES.items():
            if _src.exists():
                _dst = trader_staged / _rel
                _dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(_src, _dst)

    # --- Generate _meta.json and SKILL.md for each skill ---
    meta_templates = {
        "trader": {
            "name": "trader",
            "version": "2.4.0",
            "description": "A股单票分析 + 选股池管理（四阶段定位）",
        },
        "t0": {
            "name": "t0",
            "version": "2.4.0",
            "description": "A股盘中T0盯盘助理",
        },
        "review": {
            "name": "review",
            "version": "2.4.0",
            "description": "A股盘后复盘 + 仓位轮动 + 信号统计",
        },
    }

    for skill_slug, version, staged in stages:
        # Write _meta.json
        meta = meta_templates.get(skill_slug, {"name": skill_slug, "version": version})
        (staged / "_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        # Write SKILL.md if not already present
        skill_md_path = staged / "SKILL.md"
        if not skill_md_path.exists():
            skill_md = f"---\nname: {skill_slug}\ndescription: {meta.get('description', '')}\nversion: {version}\n---\n\n# {skill_slug}\n\n{meta.get('description', '')}\n"
            skill_md_path.write_text(skill_md, encoding="utf-8")

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

    # --- Build skill zips ---
    print("\n--- Packing Skills ---")
    for skill_slug, version, staged in stages:
        zip_name = f"{skill_slug}.zip"
        zip_path = release_dir / zip_name
        if zip_path.exists():
            zip_path.unlink()
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            add_to_zip(staged, archive, arc_prefix="")
        print(f"  -> {zip_path.relative_to(output_dir)}  ({zip_path.stat().st_size / 1024:.0f} KB)")

    # Clean up legacy zips
    for old_zip in ("trader-pool.zip", "trader-portfolio.zip", "review-trader.zip",
                    "trader-tracking.zip", "t0-trader.zip", "live-trader.zip",
                    "review-commander.zip"):
        p = release_dir / old_zip
        if p.exists():
            p.unlink()

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
            print(f"  [{skill_slug}] {zip_path.name}  meta={has_meta} scripts={has_scripts} hermes={has_hermes} skill={has_skill} digest={meta_digest[:8]} {empty_status}")

    # Cleanup temp dirs
    for _, _, staged in stages:
        shutil.rmtree(staged.parent, ignore_errors=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
