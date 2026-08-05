#!/usr/bin/env python3
"""打包各 Skill zip，按宿主分目录输出。

默认一次打两套（推荐）：
  03-安装包-dist/releases/<时间戳>/
    hermes/trader.zip …          ← 交给 Hermes；可自动装到 ~/.hermes/skills
    workbuddy/trader.zip …       ← 交给 WorkBuddy（不自动装）
    怎么用.txt

只打一套：
    python3 …/pack_all.py --host hermes
    python3 …/pack_all.py --host workbuddy --no-install
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
    # 确保目录存在
    releases_dir.mkdir(parents=True, exist_ok=True)
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

    # NOTE: Re-export stubs are no longer generated. All modules use package-relative
    # imports (trader_shared.* / .*), so the scripts/ top level no longer needs bridges.


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
    """仅安装 Hermes 宿主包到 ~/.hermes/skills（WorkBuddy 包不自动装）。"""
    hermes_dir = Path.home() / ".hermes" / "skills"
    hermes_dir.mkdir(parents=True, exist_ok=True)
    backup_dir = hermes_dir / ".backup"

    for old_skill in (
        "trader-pool",
        "trader-portfolio",
        "review-trader",
        "trader-tracking",
        "t0-trader",
        "live-trader",
        "review-commander",
    ):
        dest = hermes_dir / old_skill
        if dest.exists():
            shutil.rmtree(dest)

    print("\n--- Auto-install → ~/.hermes/skills (host=hermes only) ---")
    for skill_slug, _version, staged in stages:
        dest = hermes_dir / skill_slug
        if dest.exists():
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
        print(f"  [hermes] {meta_name} -> {dest}")


META_TEMPLATES = {
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
    "daily_briefing": {
        "name": "daily_briefing",
        "version": "1.0.0",
        "description": "A股每日简报 — 从候选池批量分析、排序、分层，输出操作建议",
    },
    "wyckoff": {
        "name": "wyckoff",
        "version": "1.0.0",
        "description": "A股威科夫结构参考卡 + 池内吸筹链排序（人读，不作交易总司令）",
    },
    "chanlun": {
        "name": "chanlun",
        "version": "1.0.0",
        "description": "A股缠论 B·中剪结构报告（日线本波 + 周线副读；人读，不作交易总司令）",
    },
}


def _write_skill_config(staged: Path, host: str) -> None:
    """写入 config.json：Tushare 密钥（若有）+ 明确 trader_host。

    取值优先级：环境变量 > 仓内 tushare_config.local.py。
    默认网关为专属 quicksync；勿把含密钥 zip 公开分发。
    """
    cfg: dict[str, str] = {"trader_host": host}

    local_vals: dict[str, str] = {}
    local_path = Path(__file__).resolve().parents[1] / "trader_shared" / "tushare_config.local.py"
    if local_path.is_file():
        try:
            import importlib.util

            spec = importlib.util.spec_from_file_location("_pack_tushare_local", local_path)
            if spec is not None and spec.loader is not None:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                for var in ("TUSHARE_TOKEN", "TUSHARE_API_URL", "TUSHARE_REALTIME_URL"):
                    val = str(getattr(mod, var, "") or "").strip()
                    if val:
                        local_vals[var] = val
        except Exception:
            local_vals = {}

    for var in ("TUSHARE_TOKEN", "TUSHARE_API_URL", "TUSHARE_REALTIME_URL"):
        val = os.environ.get(var, "").strip() or local_vals.get(var, "")
        if val:
            cfg[var.lower()] = val
    # 兜底：有 token 但没显式 URL 时，写入专属网关，避免 skill 包回落到旧官方域
    if cfg.get("tushare_token"):
        cfg.setdefault("tushare_api_url", "http://api.quicksync.cn")
        cfg.setdefault("tushare_realtime_url", "http://api.quicksync.cn")
    (staged / "config.json").write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _write_howto(release_dir: Path, hosts: list[str]) -> None:
    lines = [
        "Skill 安装包说明",
        "",
        "目录 hermes/     → 只给 Hermes Agent 用（Tushare 主源）",
        "目录 workbuddy/  → 只给 WorkBuddy Agent 用（资金流优先 Tdx）",
        "",
        "两套 zip 内容相同，仅 config.json 里的 trader_host 不同。",
        "Agent 都是：跑脚本 → 原样贴面板。",
        "",
        "Hermes：本机打包默认会自动装到 ~/.hermes/skills/",
        "WorkBuddy：把 workbuddy/ 下对应 zip 解压/导入到 WorkBuddy 技能目录。",
        "",
        f"本次打包宿主: {', '.join(hosts)}",
        "",
    ]
    (release_dir / "怎么用.txt").write_text("\n".join(lines), encoding="utf-8")


def _verify_zip(zip_path: Path, skill_slug: str) -> str:
    with zipfile.ZipFile(zip_path, "r") as archive:
        names = archive.namelist()
        prefix = f"{skill_slug}/"
        has_meta = f"{prefix}_meta.json" in names or "_meta.json" in names
        has_scripts = any(
            n.startswith(f"{prefix}scripts/") or n.startswith("scripts/") for n in names
        )
        has_hermes = f"{prefix}HERMES.md" in names or "HERMES.md" in names
        has_skill = f"{prefix}SKILL.md" in names or "SKILL.md" in names
        empty_py = [
            n
            for n in names
            if n.endswith(".py")
            and archive.getinfo(n).file_size == 0
            and not n.endswith("/__init__.py")
            and not n.endswith("__init__.py")
        ]
        empty_status = "EMPTY!" if empty_py else ""
        has_interfaces = any("interfaces.py" in n for n in names)
        has_fetchers = any("fetchers.py" in n for n in names)
        has_async_utils = any("async_utils.py" in n for n in names)
        has_plugins = any("plugins/" in n for n in names)
        meta_digest = "unknown"
        meta_path = f"{prefix}_meta.json" if f"{prefix}_meta.json" in names else "_meta.json"
        if meta_path in names:
            try:
                meta = json.loads(archive.read(meta_path).decode("utf-8"))
                meta_digest = meta.get("shared_bundle", "unknown")
            except Exception:
                meta_digest = "bad_meta"
        di_status = (
            "DI=ok"
            if has_interfaces and has_fetchers and has_async_utils and has_plugins
            else "DI=MISSING"
        )
        status = (
            "ok"
            if has_meta and has_scripts and has_hermes and has_skill and empty_status != "EMPTY!"
            else "MISSING"
        )
        return (
            f"  [{skill_slug}] {zip_path.name}  meta={has_meta} scripts={has_scripts} "
            f"hermes={has_hermes} skill={has_skill} digest={meta_digest[:8]} "
            f"{di_status} {status} {empty_status}"
        )


def main(args: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="打包 Skill：默认一次输出 hermes/ 与 workbuddy/ 两套"
    )
    parser.add_argument(
        "--host",
        choices=("hermes", "workbuddy", "both"),
        default="both",
        help="打包宿主：hermes / workbuddy / both（默认 both）",
    )
    parser.add_argument(
        "--no-install",
        action="store_true",
        help="跳过自动安装到 ~/.hermes/skills/（WorkBuddy 包本来就不自动装）",
    )
    parsed, _ = parser.parse_known_args(args if args is not None else None)

    if os.environ.get("PACK_NO_INSTALL") or "pytest" in sys.modules:
        parsed.no_install = True

    hosts = ["hermes", "workbuddy"] if parsed.host == "both" else [parsed.host]

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
    print(f"Release dir: {release_dir_name}/  hosts={hosts}")

    stages: list[tuple[str, str, Path]] = []
    skills_to_pack = ["trader", "t0", "review", "daily_briefing", "wyckoff", "chanlun"]

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
                        shutil.copytree(
                            item,
                            dst_item,
                            ignore=shutil.ignore_patterns(
                                "__pycache__", ".pytest_cache", "*.pyc", ".DS_Store"
                            ),
                        )
                else:
                    shutil.copy2(item, dst_item)

        copy_shared(staged, skill_name)
        common_rules = packages_dir / "_common" / "agent-rules.md"
        if common_rules.exists():
            refs = staged / "references"
            refs.mkdir(parents=True, exist_ok=True)
            shutil.copy2(common_rules, refs / "agent-rules.md")
        stages.append((skill_name, "2.4.0", staged))

    if stages:
        trader_staged = stages[0][2]
        extra = root / "scripts" / "t0_cron.py"
        if extra.exists():
            dst = trader_staged / "scripts" / "t0_cron.py"
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(extra, dst)

    # meta / SKILL / digest（与宿主无关，只做一次）
    for skill_slug, version, staged in stages:
        meta = dict(META_TEMPLATES.get(skill_slug, {"name": skill_slug, "version": version}))
        (staged / "_meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        skill_md_path = staged / "SKILL.md"
        if not skill_md_path.exists():
            skill_md_path.write_text(
                f"---\nname: {skill_slug}\ndescription: {meta.get('description', '')}\n"
                f"version: {version}\n---\n\n# {skill_slug}\n\n{meta.get('description', '')}\n",
                encoding="utf-8",
            )

    bundle_digests: dict[str, str] = {}
    for skill_slug, _, staged in stages:
        bundle_digests[skill_slug] = concat_digest(shared_files_for_skill(staged))
    for skill_slug, _, staged in stages:
        meta_path = staged / "_meta.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["shared_bundle"] = bundle_digests.get(skill_slug, "unknown")
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # 按宿主写 config 并分别打 zip（同一份 staged，换 config 再打）
    for host in hosts:
        host_dir = release_dir / host
        host_dir.mkdir(parents=True, exist_ok=True)
        print(f"\n--- Packing host={host} → {host_dir.relative_to(output_dir)} ---")
        for skill_slug, _version, staged in stages:
            _write_skill_config(staged, host)
            print(f"  [config] trader_host={host} ({skill_slug})")
            zip_path = host_dir / f"{skill_slug}.zip"
            if zip_path.exists():
                zip_path.unlink()
            with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                add_to_zip(staged, archive, arc_prefix=skill_slug)
            print(f"  -> {zip_path.relative_to(output_dir)}  ({zip_path.stat().st_size / 1024:.0f} KB)")

    _write_howto(release_dir, hosts)

    # 自动安装：仅 hermes 宿主，且 staged 上留下 hermes 的 config
    if "hermes" in hosts:
        for _slug, _ver, staged in stages:
            _write_skill_config(staged, "hermes")
        if parsed.no_install:
            print("\n[no-install] skipped auto-install")
        else:
            auto_install(stages)
    elif not parsed.no_install:
        print("\n[no-install] host=workbuddy only — 不装 ~/.hermes（请把 workbuddy/ 交给 WorkBuddy）")

    print("\n--- Verification ---")
    for host in hosts:
        host_dir = release_dir / host
        for skill_slug, _, _ in stages:
            zip_path = host_dir / f"{skill_slug}.zip"
            print(_verify_zip(zip_path, skill_slug))

    for _, _, staged in stages:
        shutil.rmtree(staged.parent, ignore_errors=True)

    print(f"\nDone. 给 Hermes → {release_dir / 'hermes'}")
    if "workbuddy" in hosts:
        print(f"给 WorkBuddy → {release_dir / 'workbuddy'}")
    print(f"说明 → {release_dir / '怎么用.txt'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
