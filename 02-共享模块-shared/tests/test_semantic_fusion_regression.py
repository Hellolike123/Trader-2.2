"""D4 / #1 语义级回归测试：fusion 决策路径确定性快照。

锚文件：tests/fixtures/fusion_semantic_baseline.json（改后正确行为）。
若有人把 #1 重归一化回退（或改动 fusion 加权语义），本测试会报红并给出
pre/post 字段级 diff，作为决策正确性的安全网。

零网络：场景用合成三卡直接喂 merge_decisions(analysis_cards=...)。
"""
from __future__ import annotations

import json
from pathlib import Path

from tests.fusion_regression_helpers import SCENARIOS, capture_all

_FIXTURE = Path(__file__).parent / "fixtures" / "fusion_semantic_baseline.json"


def _load_baseline() -> dict:
    return json.loads(_FIXTURE.read_text(encoding="utf-8")).get("fingerprints", {})


def test_fusion_semantic_baseline_stable():
    """改后基线须稳定：任何 fusion 加权/分歧语义变化都会在此报红。"""
    baseline = _load_baseline()
    current = capture_all()
    assert set(current.keys()) == set(baseline.keys()), "场景集合漂移"
    mismatches = []
    for name in current:
        a = current[name]
        b = baseline[name]
        for k in a:
            if a[k] != b.get(k):
                mismatches.append(f"  [{name}] {k}: current={a[k]} baseline={b.get(k)}")
    if mismatches:
        raise AssertionError(
            "fusion 决策指纹与基线不一致（疑似 #1 重归一化被回退或加权语义变更）：\n"
            + "\n".join(mismatches)
        )


def test_momentum_insufficient_stripped_from_weights():
    """#1 不变量：动量 insufficient 时权重须剥离（weights_used.momentum==0），
    且真中性/多空场景动量权重须保留（>0）。"""
    baseline = _load_baseline()
    for scn in SCENARIOS:
        name = scn["name"]
        wu = baseline[name]["weights_used"]
        if scn.get("changed_by_fix"):
            assert wu["momentum"] == 0.0, f"{name}: insufficient 动量权重应被剥离，实际 {wu['momentum']}"
        else:
            assert wu["momentum"] > 0.0, f"{name}: 非 insufficient 场景动量权重应保留，实际 {wu['momentum']}"


def test_insufficient_dominates_over_neutral():
    """#1 语义：动量不足但 chan+vpf 同多，应比「动量真中性同多」更强或相等
    （不足席被剥离后 chan/vpf 主导，而非被死权重稀释）。"""
    baseline = _load_baseline()
    insuf = baseline["mom_insufficient_chan_vpf_bull"]["weighted_score"]
    neutral = baseline["mom_real_neutral_chan_bull"]["weighted_score"]
    assert insuf >= neutral, (
        f"insufficient 场景应 >= 真中性场景（chan/vpf 主导），"
        f"got insuf={insuf} neutral={neutral}"
    )
    # insufficient 场景 action 不应弱于真中性（都应是做多导向）
    assert baseline["mom_insufficient_chan_vpf_bull"]["action"] in (
        "半仓试 (多方主导)", "增持", "等转强观察"
    )
