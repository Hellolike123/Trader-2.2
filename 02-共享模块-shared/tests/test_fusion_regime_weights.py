"""融合层 Regime 权重外置 yaml 的加载与回退测试（P0-2）。

验证:
  1. yaml 文件存在且可解析，内容等于历史默认值
  2. 运行时 REGIME_WEIGHTS 等于预期（默认环境下 yaml 成功加载）
  3. 未知 regime 仍回退到"正常"（回归 test_fusion_core 既有契约）
  4. yaml 缺失 / 损坏 / 自定义覆盖时，加载器行为正确
"""
from __future__ import annotations

from pathlib import Path

import pytest

from trader_shared import fusion_regime as fr

EXPECTED = {
    "正常": {"chan": 0.3, "momentum": 0.45, "vpf": 0.25},
    "偏弱": {"chan": 0.5, "momentum": 0.15, "vpf": 0.35},
    "很差": {"chan": 0.0, "momentum": 0.0, "vpf": 0.0},
    "未知": {"chan": 0.3, "momentum": 0.45, "vpf": 0.25},
}


def test_yaml_file_present():
    assert fr._YAML_PATH.exists(), f"权重 yaml 缺失: {fr._YAML_PATH}"


def test_yaml_matches_expected():
    yaml = pytest.importorskip("yaml")
    with open(fr._YAML_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    assert data.get("regime_weights") == EXPECTED


def test_runtime_weights_match_expected():
    # 默认环境下 yaml 应被成功加载，且等于历史默认值（兜底值亦与之相等，故即便
    # 无 pyyaml 也不会漂移——但本环境已装 pyyaml，验证的是真实加载路径）
    assert fr.REGIME_WEIGHTS == EXPECTED


def test_unknown_regime_falls_back_to_normal():
    # 回归 test_fusion_core.py:435 的既有契约
    assert fr.get_regime_weights("未知状态") == fr.get_regime_weights("正常")


def test_loader_reads_custom_yaml(tmp_path, monkeypatch):
    # 证明加载器确实读 yaml（而非只走兜底）：用自定义值覆盖"正常"
    yaml = pytest.importorskip("yaml")
    custom = tmp_path / "fusion_regime_weights.yaml"
    custom.write_text(
        "regime_weights:\n"
        "  正常:\n"
        "    chan: 0.1\n"
        "    momentum: 0.2\n"
        "    vpf: 0.7\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(fr, "_YAML_PATH", custom)
    loaded = fr._load_regime_weights()
    assert loaded["正常"] == {"chan": 0.1, "momentum": 0.2, "vpf": 0.7}
    # 未出现在 yaml 中的 regime 保留兜底
    assert loaded["偏弱"] == fr._FALLBACK_REGIME_WEIGHTS["偏弱"]


def test_loader_fallback_on_missing_yaml(monkeypatch):
    monkeypatch.setattr(
        fr, "_YAML_PATH", Path("/nonexistent/fusion_regime_weights.yaml")
    )
    loaded = fr._load_regime_weights()
    assert loaded == fr._FALLBACK_REGIME_WEIGHTS
    # 未知 regime 仍能回退到"正常"
    assert loaded.get("未知") == loaded["正常"]


def test_loader_fallback_on_corrupt_yaml(tmp_path, monkeypatch):
    bad = tmp_path / "fusion_regime_weights.yaml"
    bad.write_text(": : : not valid :::\n  - [", encoding="utf-8")
    monkeypatch.setattr(fr, "_YAML_PATH", bad)
    loaded = fr._load_regime_weights()
    assert loaded == fr._FALLBACK_REGIME_WEIGHTS
