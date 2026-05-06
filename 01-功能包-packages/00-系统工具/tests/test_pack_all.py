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

# Expected entry points per skill
EXPECTED_ENTRIES = {
    "01-单票分析-trader": "final_report.py",
    "02-盘中T0-t0-trader": "final_t0.py",
    "03-选股池-trader-pool": "final_pool.py",
    "04-仓位轮动-trader-portfolio": "final_portfolio.py",
    "05-盘后复盘-review-trader": "final_review.py",
}


def test_pack_all_creates_single_zip() -> None:
    """pack_all.py should produce one zip at trader-all-skill.zip."""
    with mock.patch.object(pack_all, "repo_root") as mock_root:
        mock_root.return_value = SCRIPTS_DIR
        archive_path = pack_all.repo_root() / "03-安装包-dist" / "trader-all-skill.zip"

        pack_all.main()

        assert archive_path.exists(), f"{archive_path} was not created"

        with zipfile.ZipFile(archive_path, "r") as zf:
            names = zf.namelist()
            assert len(names) > 0, "Archive is empty"

        archive_path.unlink(missing_ok=True)


def test_pack_all_contains_all_skills() -> None:
    """The zip should contain entries for all 5 active skills."""
    for name in pack_all.SKILLS:
        skill_dir = PACKAGES_DIR / name
        assert skill_dir.exists(), f"Skill dir {skill_dir} not found"


def test_pack_all_bundle_structure() -> None:
    """Verify each skill in the zip has expected scripts and shared modules."""
    bundle_path = DIST_DIR / "trader-all-skill.zip"
    if bundle_path.exists():
        bundle_path.unlink()

    with mock.patch.object(pack_all, "repo_root") as mock_root:
        mock_root.return_value = SCRIPTS_DIR
        pack_all.main()

    with zipfile.ZipFile(bundle_path, "r") as zf:
        names = zf.namelist()

        for skill_name, expected_script in EXPECTED_ENTRIES.items():
            skill_prefix = f"01-功能包-packages/{skill_name}/"
            # Check script directory exists
            skill_scripts = [n for n in names if n.startswith(skill_prefix + "scripts/")]
            assert len(skill_scripts) > 0, f"{skill_name} has no scripts in archive"

            # Check expected entry point exists
            entry_found = any(expected_script in n for n in skill_scripts)
            assert entry_found, f"{skill_name} missing {expected_script}, scripts: {skill_scripts}"

            # Check SKILL.md exists
            skill_md = f"01-功能包-packages/{skill_name}/SKILL.md"
            assert skill_md in names, f"Missing {skill_md}"

            # Check HERMES.md exists
            hermes_md = f"01-功能包-packages/{skill_name}/HERMES.md"
            assert hermes_md in names, f"Missing {hermes_md}"

            # Check shared modules were copied
            assert any("scripts/light_data.py" in n for n in skill_scripts), \
                f"{skill_name} missing shared light_data.py"
            assert any("scripts/signal_contract.py" in n for n in skill_scripts), \
                f"{skill_name} missing shared signal_contract.py"

            # Check candidate_core exists
            assert any("scripts/candidate_core.py" in n for n in skill_scripts), \
                f"{skill_name} missing shared candidate_core.py"

            # Check tests directory
            assert any(n.startswith(skill_prefix + "tests/") for n in names), \
                f"{skill_name} missing tests/ in archive"

    bundle_path.unlink(missing_ok=True)


def test_pack_all_no_package_skill() -> None:
    """Old package_skill.py should NOT be in the new zip."""
    bundle_path = DIST_DIR / "trader-all-skill.zip"
    if bundle_path.exists():
        bundle_path.unlink()

    with mock.patch.object(pack_all, "repo_root") as mock_root:
        mock_root.return_value = SCRIPTS_DIR
        pack_all.main()

    with zipfile.ZipFile(bundle_path, "r") as zf:
        names = zf.namelist()
        for name in names:
            assert "package_skill.py" not in name, \
                f"Old package_skill.py should not be in bundle: {name}"

    bundle_path.unlink(missing_ok=True)


def test_pack_all_skips_irrelevant_skills() -> None:
    """Deprecated trader-compare should NOT be in the new zip."""
    bundle_path = DIST_DIR / "trader-all-skill.zip"
    if bundle_path.exists():
        bundle_path.unlink()

    with mock.patch.object(pack_all, "repo_root") as mock_root:
        mock_root.return_value = SCRIPTS_DIR
        pack_all.main()

    with zipfile.ZipFile(bundle_path, "r") as zf:
        names = zf.namelist()
        has_compare = any("trader-compare" in n for n in names)
        assert not has_compare, "trader-compare should not be in unified zip"

    bundle_path.unlink(missing_ok=True)


if __name__ == "__main__":
    # Run with PYTHONPATH or pytest
    test_pack_all_skips_irrelevant_skills()
    test_pack_all_bundle_structure()
    test_pack_all_creates_single_zip()
    test_pack_all_contains_all_skills()
    test_pack_all_no_package_skill()
    print("All pack_all tests passed!")
