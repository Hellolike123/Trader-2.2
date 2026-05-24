#!/usr/bin/env python3
"""Tests for pack_all.py — bundle digest consistency."""
from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path


# We'll create a minimal staged bundle in the test itself,
# so pack_all.py doesn't need to be imported directly.
PACK_ALL_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(PACK_ALL_DIR) not in sys.path:
    sys.path.insert(0, str(PACK_ALL_DIR))


_REPOS = Path(__file__).resolve().parents[2] / "03-安装包-dist" / "releases"


class TestComputeFileSha256:
    """Helper function computes deterministic SHA-256."""

    def test_deterministic(self):
        from pack_all import compute_file_sha256

        # Create a temp file
        tmp = Path(__file__).parent / "test_hash_data.txt"
        tmp.write_text("hello world")
        try:
            h1 = compute_file_sha256(tmp)
            h2 = compute_file_sha256(tmp)
            assert h1 == h2
            assert len(h1) == 64  # full hex SHA-256
            assert h1 != "0" * 64
        finally:
            tmp.unlink(missing_ok=True)

    def test_empty_file(self):
        from pack_all import compute_file_sha256

        tmp = Path(__file__).parent / "test_empty.txt"
        tmp.write_text("")
        try:
            h = compute_file_sha256(tmp)
            assert len(h) == 64
            assert h != "0" * 64  # sha256 of empty string is not all zeros
        finally:
            tmp.unlink(missing_ok=True)

    def test_nonexistent_file(self):
        from pack_all import compute_file_sha256

        h = compute_file_sha256(Path("/nonexistent/path/file.py"))
        assert h == "0" * 64


class TestConcatDigest:
    """Hash of sorted values produces consistent digest."""

    def test_same_values_same_digest(self):
        from pack_all import concat_digest

        shares1 = {"a": "hash1", "b": "hash2"}
        shares2 = {"b": "hash2", "a": "hash1"}
        assert concat_digest(shares1) == concat_digest(shares2)

    def test_different_values_different_digest(self):
        from pack_all import concat_digest

        shares1 = {"a": "hash1"}
        shares2 = {"a": "hash2"}
        assert concat_digest(shares1) != concat_digest(shares2)

    def test_length_is_16(self):
        from pack_all import concat_digest

        shares = {"a": "h1"}
        dig = concat_digest(shares)
        assert len(dig) == 16


class TestSharedFilesForSkill:
    """Extracts file hashes from the actual staged bundle."""

    def extract_digest_from_zip(self, zip_path: Path) -> str:
        """Read share_bundle digest from _meta.json inside zip."""
        with zipfile.ZipFile(zip_path, "r") as zf:
            meta = json.loads(zf.read("_meta.json"))
            return meta.get("shared_bundle", "unknown")

    def _find_latest_release(self) -> Path:
        """Find the latest release directory by sorting."""
        releases_dir = _REPOS
        dirs = sorted(
            [d for d in releases_dir.iterdir() if d.is_dir() and d.name not in (".gitkeep",)],
            reverse=True,
        )
        return dirs[0] if dirs else Path()

    def test_digest_present_in_each_zip(self):
        """Each skill zip's _meta.json must contain shared_bundle."""
        latest = self._find_latest_release()
        assert latest.exists(), "No release directories found"

        expected_skills = {"trader", "t0-trader", "trader-pool", "trader-portfolio", "review-trader", "trader-tracking"}
        missing = []
        for skill in expected_skills:
            zip_path = latest / f"{skill}.zip"
            if not zip_path.exists():
                missing.append(f"{skill}.zip not found")
                continue
            dig = self.extract_digest_from_zip(zip_path)
            if dig == "unknown":
                missing.append(f"{skill}.zip has no shared_bundle")
            if dig == "bad_meta":
                missing.append(f"{skill}.zip has bad _meta.json")

        assert missing == [], f"Digest issues in latest release {latest.name}: " + "; ".join(missing)

    def test_non_t0_skills_share_digest(self):
        """All non-t0 skills should share the same digest."""
        release_dirs = sorted([d for d in _REPOS.iterdir() if d.is_dir()], reverse=True)
        assert len(release_dirs) >= 1, "No release directories found"
        latest = release_dirs[0]

        non_t0 = {"trader", "trader-pool", "trader-portfolio", "review-trader", "trader-tracking"}

        digests = {}
        for skill in non_t0:
            zip_path = latest / f"{skill}.zip"
            if zip_path.exists():
                dig = self.extract_digest_from_zip(zip_path)
                digests[skill] = dig

        # All non-t0 should agree
        unique = set(digests.values())
        if len(digests) > 1:
            assert len(unique) == 1, f"Non-t0 digests differ: {digests}"


class TestPackAllNoEmptyFiles:
    """No .py file should be 0 bytes in any released zip."""

    def extract_empty_py_from_zip(self, zip_path: Path) -> list[str]:
        """List names of .py files with 0 size in the zip."""
        empty = []
        with zipfile.ZipFile(zip_path, "r") as zf:
            for name in zf.namelist():
                if name.endswith(".py"):
                    info = zf.getinfo(name)
                    if info.file_size == 0:
                        empty.append(name)
        return empty

    def test_no_empty_py_in_any_zip(self):
        release_dirs = sorted([d for d in _REPOS.iterdir() if d.is_dir()], reverse=True)
        assert len(release_dirs) >= 1, "No release directories found"
        latest = release_dirs[0]

        for zip_name in latest.glob("*.zip"):
            empty = self.extract_empty_py_from_zip(zip_name)
            assert empty == [], f"{zip_name.name} has empty .py files: {empty}"
