#!/usr/bin/env python3
"""Tests for pack_all.py — validates the unified zip bundle."""
from __future__ import annotations

import re
import shutil
import sys
import zipfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1].parent.parent / "02-共享模块-shared" / "scripts"))

import pack_all

SCRIPTS_DIR = Path(__file__).resolve().parents[3]
PACKAGES_DIR = SCRIPTS_DIR / "01-功能包-packages"
DIST_DIR = SCRIPTS_DIR / "03-安装包-dist"
RELEASES_DIR = DIST_DIR / "releases"
RELEASE_DIR_PATTERN = re.compile(r"^\d{4}-\d{6}$")

EXPECTED_SKILLS: list[tuple[str, str, str]] = [
    ("01-单票分析-trader", "trader", "final_report.py"),
    ("02-盘中T0-t0-trader", "t0-trader", "final_t0.py"),
    ("03-选股池-trader-pool", "trader-pool", "final_pool.py"),
    ("04-仓位轮动-trader-portfolio", "trader-portfolio", "final_portfolio.py"),
    ("05-盘后复盘-review-trader", "review-trader", "final_review.py"),
]


def _verify_skill_zip(zf: zipfile.ZipFile, slug: str, expected_script: str) -> None:
    names = zf.namelist()
    assert "_meta.json" in names, f"{slug} missing _meta.json"
    assert "HERMES.md" in names, f"{slug} missing HERMES.md"
    assert "SKILL.md" in names, f"{slug} missing SKILL.md"
    script_entries = [n for n in names if n.startswith("scripts/")]
    assert len(script_entries) > 0, f"{slug} has no scripts/ entries"
    assert any(expected_script in n for n in script_entries), f"{slug} missing {expected_script}"
    assert any("light_data.py" in n for n in script_entries), f"{slug} missing light_data.py"
    assert any("signal_contract.py" in n for n in script_entries), f"{slug} missing signal_contract.py"
    assert any("candidate_core.py" in n for n in script_entries), f"{slug} missing candidate_core.py"
    assert any("chan_core.py" in n for n in script_entries), f"{slug} missing chan_core.py"
    assert any("wyckoff_core.py" in n for n in script_entries), f"{slug} missing wyckoff_core.py"
    assert any("momentum_core.py" in n for n in script_entries), f"{slug} missing momentum_core.py"


def _verify_combined_zip(zf: zipfile.ZipFile, slug: str, expected_script: str) -> None:
    names = zf.namelist()
    prefix = f"{slug}/"
    assert f"{prefix}_meta.json" in names, f"{slug} missing _meta.json in combined"
    assert f"{prefix}HERMES.md" in names, f"{slug} missing HERMES.md in combined"
    assert f"{prefix}SKILL.md" in names, f"{slug} missing SKILL.md in combined"
    script_entries = [n for n in names if n.startswith(f"{prefix}scripts/")]
    assert len(script_entries) > 0, f"{slug} has no scripts/ entries in combined"
    assert any(expected_script in n for n in script_entries), f"{slug} missing {expected_script} in combined"
    assert any("light_data.py" in n for n in script_entries), f"{slug} missing light_data.py"
    assert any("signal_contract.py" in n for n in script_entries), f"{slug} missing signal_contract.py"
    assert any("candidate_core.py" in n for n in script_entries), f"{slug} missing candidate_core.py"
    assert any("chan_core.py" in n for n in script_entries), f"{slug} missing chan_core.py"
    assert any("wyckoff_core.py" in n for n in script_entries), f"{slug} missing wyckoff_core.py"
    assert any("momentum_core.py" in n for n in script_entries), f"{slug} missing momentum_core.py"


def _clean_stale_releases() -> None:
    """Clean all release dirs under releases/ (not the old flat layout)."""
    for entry in RELEASES_DIR.iterdir():
        if entry.is_dir() and entry.name != ".gitkeep":
            if RELEASE_DIR_PATTERN.match(entry.name):
                shutil.rmtree(str(entry))


def _get_release_dirs() -> list[Path]:
    if not RELEASES_DIR.exists():
        return []
    return sorted(d for d in RELEASES_DIR.iterdir() if d.is_dir() and RELEASE_DIR_PATTERN.match(d.name))


def test_pack_all_creates_individual_zips() -> None:
    _clean_stale_releases()
    with mock.patch.object(pack_all, "repo_root") as mock_root:
        mock_root.return_value = SCRIPTS_DIR
        pack_all.main()
    release_dirs = _get_release_dirs()
    assert len(release_dirs) >= 1, "No release dir found"
    release_dir = release_dirs[-1]
    for _, slug, _ in EXPECTED_SKILLS:
        zip_path = release_dir / f"{slug}.zip"
        assert zip_path.exists(), f"No zip found for {slug}"
        with zipfile.ZipFile(zip_path, "r") as zf:
            assert len(zf.namelist()) > 0, f"{zip_path.name} is empty"


def test_pack_all_creates_combined_zip() -> None:
    _clean_stale_releases()
    with mock.patch.object(pack_all, "repo_root") as mock_root:
        mock_root.return_value = SCRIPTS_DIR
        pack_all.main()
    release_dirs = _get_release_dirs()
    assert len(release_dirs) >= 1, "No release dir found"
    combined_path = release_dirs[-1] / "trader-all-skill.zip"
    assert combined_path.exists(), "No combined zip found"
    with zipfile.ZipFile(combined_path, "r") as zf:
        assert len(zf.namelist()) > 0, "Combined archive is empty"


def test_pack_all_contains_all_skills() -> None:
    for dir_name, _slug, _script in EXPECTED_SKILLS:
        skill_dir = PACKAGES_DIR / dir_name
        assert skill_dir.exists(), f"Skill dir {skill_dir} not found"


def test_pack_all_individual_structure() -> None:
    _clean_stale_releases()
    with mock.patch.object(pack_all, "repo_root") as mock_root:
        mock_root.return_value = SCRIPTS_DIR
        pack_all.main()
    release_dirs = _get_release_dirs()
    assert len(release_dirs) >= 1, "No release dir found"
    release_dir = release_dirs[-1]
    for dir_name, slug, expected_script in EXPECTED_SKILLS:
        zip_path = release_dir / f"{slug}.zip"
        assert zip_path.exists(), f"Expected {slug}.zip not found"
        with zipfile.ZipFile(zip_path, "r") as zf:
            _verify_skill_zip(zf, slug, expected_script)


def test_pack_all_combined_structure() -> None:
    _clean_stale_releases()
    with mock.patch.object(pack_all, "repo_root") as mock_root:
        mock_root.return_value = SCRIPTS_DIR
        pack_all.main()
    release_dirs = _get_release_dirs()
    assert len(release_dirs) >= 1, "No release dir found"
    combined_path = release_dirs[-1] / "trader-all-skill.zip"
    assert combined_path.exists(), "No combined zip found"
    with zipfile.ZipFile(combined_path, "r") as zf:
        for dir_name, slug, expected_script in EXPECTED_SKILLS:
            _verify_combined_zip(zf, slug, expected_script)


def test_pack_all_no_package_skill() -> None:
    _clean_stale_releases()
    with mock.patch.object(pack_all, "repo_root") as mock_root:
        mock_root.return_value = SCRIPTS_DIR
        pack_all.main()
    release_dirs = _get_release_dirs()
    assert len(release_dirs) >= 1, "No release dir found"
    release_dir = release_dirs[-1]

    combined_path = release_dir / "trader-all-skill.zip"
    assert combined_path.exists()
    with zipfile.ZipFile(combined_path, "r") as zf:
        for name in zf.namelist():
            assert "package_skill.py" not in name, f"Old package_skill.py should not be in bundle: {name}"

    for _, slug, _ in EXPECTED_SKILLS:
        zip_path = release_dir / f"{slug}.zip"
        if zip_path.exists():
            with zipfile.ZipFile(zip_path, "r") as zf:
                for name in zf.namelist():
                    assert "package_skill.py" not in name, f"Old package_skill.py should not be in {slug}: {name}"


def test_pack_all_skips_irrelevant_skills() -> None:
    _clean_stale_releases()
    with mock.patch.object(pack_all, "repo_root") as mock_root:
        mock_root.return_value = SCRIPTS_DIR
        pack_all.main()
    release_dirs = _get_release_dirs()
    assert len(release_dirs) >= 1, "No release dir found"
    release_dir = release_dirs[-1]

    combined_path = release_dir / "trader-all-skill.zip"
    assert combined_path.exists()
    with zipfile.ZipFile(combined_path, "r") as zf:
        has_compare = any("trader-compare" in n for n in zf.namelist())
        assert not has_compare, "trader-compare should not be in unified zip"

    for _, slug, _ in EXPECTED_SKILLS:
        zip_path = release_dir / f"{slug}.zip"
        if zip_path.exists():
            with zipfile.ZipFile(zip_path, "r") as zf:
                has_compare = any("trader-compare" in n for n in zf.namelist())
                assert not has_compare, f"trader-compare should not be in {slug}"


def test_pack_all_cleanup_old_releases() -> None:
    """cleanup_old_releases should remove oldest dirs, keeping only MAX_RELEASES."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        releases = Path(tmp)
        # Create 8 fake release dirs
        for i in range(8):
            (releases / f"0513-16010{i}").mkdir()
        removed = pack_all.cleanup_old_releases(releases, keep=5)
        assert removed == 3, f"Expected 3 removed, got {removed}"
        remaining = sorted(d.name for d in releases.iterdir() if d.is_dir())
        assert len(remaining) == 5
        assert remaining[0] == "0513-160103"


def test_pack_all_ensure_gitignore() -> None:
    """ensure_releases_gitignore should create .gitignore with correct content."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        releases = Path(tmp) / "releases"
        pack_all.ensure_releases_gitignore(releases)
        gitignore = releases / ".gitignore"
        assert gitignore.exists()
        content = gitignore.read_text(encoding="utf-8")
        assert "*" in content
        assert "!.gitignore" in content


if __name__ == "__main__":
    test_pack_all_skips_irrelevant_skills()
    test_pack_all_combined_structure()
    test_pack_all_individual_structure()
    test_pack_all_creates_individual_zips()
    test_pack_all_creates_combined_zip()
    test_pack_all_contains_all_skills()
    test_pack_all_no_package_skill()
    test_pack_all_cleanup_old_releases()
    test_pack_all_ensure_gitignore()
    print("All pack_all tests passed!")
