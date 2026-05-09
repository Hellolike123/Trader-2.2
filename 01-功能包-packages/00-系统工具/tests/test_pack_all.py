#!/usr/bin/env python3
"""Tests for pack_all.py — validates the unified zip bundle."""
from __future__ import annotations

import os
import sys
import tempfile
import zipfile
from pathlib import Path
from unittest import mock

# Add shared scripts to path so pack_all can import
sys.path.insert(0, str(Path(__file__).resolve().parents[1].parent.parent / "02-共享模块-shared" / "scripts"))

import pack_all


SCRIPTS_DIR = Path(__file__).resolve().parents[3]
PACKAGES_DIR = SCRIPTS_DIR / "01-功能包-packages"
DIST_DIR = SCRIPTS_DIR / "03-安装包-dist"
RELEASE_DIR = DIST_DIR / "releases"

# (dir_name, slug) → entry script
EXPECTED_SKILLS: list[tuple[str, str, str]] = [
    ("01-单票分析-trader", "trader", "final_report.py"),
    ("02-盘中T0-t0-trader", "t0-trader", "final_t0.py"),
    ("03-选股池-trader-pool", "trader-pool", "final_pool.py"),
    ("04-仓位轮动-trader-portfolio", "trader-portfolio", "final_portfolio.py"),
    ("05-盘后复盘-review-trader", "review-trader", "final_review.py"),
]


def _verify_skill_zip(zf: zipfile.ZipFile, slug: str, expected_script: str) -> None:
    """Verify a single skill zip has correct flat structure."""
    names = zf.namelist()

    # Root-level files
    assert "_meta.json" in names, f"{slug} missing _meta.json"
    assert "HERMES.md" in names, f"{slug} missing HERMES.md"
    assert "SKILL.md" in names, f"{slug} missing SKILL.md"

    # Scripts
    script_entries = [n for n in names if n.startswith("scripts/")]
    assert len(script_entries) > 0, f"{slug} has no scripts/ entries"
    assert any(expected_script in n for n in script_entries), \
        f"{slug} missing {expected_script}"

    # Shared modules
    assert any("light_data.py" in n for n in script_entries), f"{slug} missing light_data.py"
    assert any("signal_contract.py" in n for n in script_entries), f"{slug} missing signal_contract.py"
    assert any("candidate_core.py" in n for n in script_entries), f"{slug} missing candidate_core.py"
    # Theory modules
    assert any("chan_core.py" in n for n in script_entries), f"{slug} missing chan_core.py"
    assert any("wyckoff_core.py" in n for n in script_entries), f"{slug} missing wyckoff_core.py"
    assert any("momentum_core.py" in n for n in script_entries), f"{slug} missing momentum_core.py"


def _verify_combined_zip(zf: zipfile.ZipFile, slug: str, expected_script: str) -> None:
    """Verify a skill in the combined zip has correct {slug}/ prefix structure."""
    names = zf.namelist()
    prefix = f"{slug}/"

    assert f"{prefix}_meta.json" in names, f"{slug} missing _meta.json in combined"
    assert f"{prefix}HERMES.md" in names, f"{slug} missing HERMES.md in combined"
    assert f"{prefix}SKILL.md" in names, f"{slug} missing SKILL.md in combined"

    script_entries = [n for n in names if n.startswith(f"{prefix}scripts/")]
    assert len(script_entries) > 0, f"{slug} has no scripts/ entries in combined"
    assert any(expected_script in n for n in script_entries), \
        f"{slug} missing {expected_script} in combined"

    assert any("light_data.py" in n for n in script_entries), f"{slug} missing light_data.py"
    assert any("signal_contract.py" in n for n in script_entries), f"{slug} missing signal_contract.py"
    assert any("candidate_core.py" in n for n in script_entries), f"{slug} missing candidate_core.py"
    assert any("chan_core.py" in n for n in script_entries), f"{slug} missing chan_core.py"
    assert any("wyckoff_core.py" in n for n in script_entries), f"{slug} missing wyckoff_core.py"
    assert any("momentum_core.py" in n for n in script_entries), f"{slug} missing momentum_core.py"


def _clean_stale_releases() -> None:
    """Remove all existing release zips so glob only sees current run."""
    for f in RELEASE_DIR.glob("*.zip"):
        f.unlink(missing_ok=True)


def _clean_stale_releases() -> None:
    for f in RELEASE_DIR.iterdir():
        if f.suffix in {".zip", ".json"} and "trader" in f.name:
            f.unlink(missing_ok=True)


def test_pack_all_creates_individual_zips() -> None:
    """pack_all.py should produce individual zips for each skill."""
    _clean_stale_releases()
    with mock.patch.object(pack_all, "repo_root") as mock_root:
        mock_root.return_value = SCRIPTS_DIR
        pack_all.main()

        import json
        manifest_file = list(RELEASE_DIR.glob("release-manifest-*.json"))[-1]
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        for _, slug, _ in EXPECTED_SKILLS:
            entry = next(e for e in manifest["entries"] if e["skill"] == slug)
            release_zip = list(RELEASE_DIR.glob(f"{slug}-{entry['version']}-*.zip"))
            assert len(release_zip) == 1, f"No release zip found for {slug}"
            with zipfile.ZipFile(release_zip[0], "r") as zf:
                assert len(zf.namelist()) > 0, f"{release_zip[0]} is empty"


def test_pack_all_creates_combined_zip() -> None:
    """pack_all.py should produce one combined zip."""
    _clean_stale_releases()
    with mock.patch.object(pack_all, "repo_root") as mock_root:
        mock_root.return_value = SCRIPTS_DIR
        pack_all.main()

        combined_zips = list(RELEASE_DIR.glob("trader-all-skill-*.zip"))
        assert len(combined_zips) == 1, f"Expected 1 combined zip, got {len(combined_zips)}"
        with zipfile.ZipFile(combined_zips[0], "r") as zf:
            assert len(zf.namelist()) > 0, "Combined archive is empty"


def test_pack_all_contains_all_skills() -> None:
    """All 5 active skill source dirs must exist."""
    for dir_name, _slug, _script in EXPECTED_SKILLS:
        skill_dir = PACKAGES_DIR / dir_name
        assert skill_dir.exists(), f"Skill dir {skill_dir} not found"


def test_pack_all_individual_structure() -> None:
    """Each individual skill zip must have flat structure (files at root)."""
    _clean_stale_releases()
    with mock.patch.object(pack_all, "repo_root") as mock_root:
        mock_root.return_value = SCRIPTS_DIR
        pack_all.main()

    import json
    manifest_files = list(RELEASE_DIR.glob("release-manifest-*.json"))
    manifest = json.loads(manifest_files[-1].read_text(encoding="utf-8"))
    for dir_name, slug, expected_script in EXPECTED_SKILLS:
        entry = next(e for e in manifest["entries"] if e["skill"] == slug)
        version = entry["version"]
        # Find zip matching version+timestamp
        release_zips = list(RELEASE_DIR.glob(f"{slug}-{version}-*.zip"))
        assert len(release_zips) == 1, f"Expected exactly 1 zip for {slug}-{version}, got {len(release_zips)}"
        with zipfile.ZipFile(release_zips[0], "r") as zf:
            _verify_skill_zip(zf, slug, expected_script)


def test_pack_all_combined_structure() -> None:
    """Combined zip must use {slug}/ prefix for each skill."""
    with mock.patch.object(pack_all, "repo_root") as mock_root:
        mock_root.return_value = SCRIPTS_DIR
        pack_all.main()

    combined_zips = list(RELEASE_DIR.glob("trader-all-skill-*.zip"))
    assert len(combined_zips) >= 1, "No combined zip found"
    combined_path = combined_zips[-1]
    with zipfile.ZipFile(combined_path, "r") as zf:
        for dir_name, slug, expected_script in EXPECTED_SKILLS:
            _verify_combined_zip(zf, slug, expected_script)

    combined_path.unlink(missing_ok=True)


def test_pack_all_no_package_skill() -> None:
    """Old package_skill.py should NOT be in any zip."""
    with mock.patch.object(pack_all, "repo_root") as mock_root:
        mock_root.return_value = SCRIPTS_DIR
        pack_all.main()

    combined_zips = list(RELEASE_DIR.glob("trader-all-skill-*.zip"))
    assert len(combined_zips) >= 1, "No combined zip found"
    combined_path = combined_zips[-1]

    # Check combined zip
    with zipfile.ZipFile(combined_path, "r") as zf:
        for name in zf.namelist():
            assert "package_skill.py" not in name, \
                f"Old package_skill.py should not be in bundle: {name}"

    # Check individual zips
    for _, slug, _ in EXPECTED_SKILLS:
        release_zips = list(RELEASE_DIR.glob(f"{slug}-*.zip"))
        if release_zips:
            with zipfile.ZipFile(release_zips[-1], "r") as zf:
                for name in zf.namelist():
                    assert "package_skill.py" not in name, \
                        f"Old package_skill.py should not be in {slug}: {name}"

    combined_path.unlink(missing_ok=True)


def test_pack_all_skips_irrelevant_skills() -> None:
    """Deprecated trader-compare should NOT be in any zip."""
    with mock.patch.object(pack_all, "repo_root") as mock_root:
        mock_root.return_value = SCRIPTS_DIR
        pack_all.main()

    # Check combined zip
    combined_zips = list(RELEASE_DIR.glob("trader-all-skill-*.zip"))
    assert len(combined_zips) >= 1, "No combined zip found"
    with zipfile.ZipFile(combined_zips[-1], "r") as zf:
        has_compare = any("trader-compare" in n for n in zf.namelist())
        assert not has_compare, "trader-compare should not be in unified zip"

    # Check individual zips
    for _, slug, _ in EXPECTED_SKILLS:
        release_zips = list(RELEASE_DIR.glob(f"{slug}-*.zip"))
        if release_zips:
            with zipfile.ZipFile(release_zips[-1], "r") as zf:
                has_compare = any("trader-compare" in n for n in zf.namelist())
                assert not has_compare, f"trader-compare should not be in {slug}"

    combined_zips[-1].unlink(missing_ok=True)


if __name__ == "__main__":
    test_pack_all_skips_irrelevant_skills()
    test_pack_all_combined_structure()
    test_pack_all_individual_structure()
    test_pack_all_creates_individual_zips()
    test_pack_all_creates_combined_zip()
    test_pack_all_contains_all_skills()
    test_pack_all_no_package_skill()
    print("All pack_all tests passed!")
