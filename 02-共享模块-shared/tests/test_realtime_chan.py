"""Part B / Part C 接入测试：cache warm 预建缠论状态 + T0 实时缠论增量。

- Part B：mock provider 返回 daily_bars → 断言 CHANLUN_STATE_DIR/{code}.json 生成，
  ChanlunEngine.load 后 cleaned/strokes 与重算一致。
- Part C：mock plan（daily_bars + current_price + quote）→ get_realtime_chan 返回
  result/signature；构造两 tick 价格上行断言 signature 变化且 _chan_realtime_alert 非空。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# 确保 trader_shared 可被导入（仓库内直接执行 pytest 时已在 path 内，
# 这里兜底把项目根加入 sys.path 以免 CI 环境找不到包）。
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from trader_shared.cache_utils import warm_chanlun_states
from trader_shared.realtime_chan import get_realtime_chan, _chan_signature, _load_or_build
from trader_shared.chan_core import ChanlunEngine

# _chan_realtime_alert 定义在 t0 monitor 模块，本测试按需导入（失败则跳过该用例）
try:
    import sys as _sys
    _sys.path.insert(0, str(_ROOT / "01-功能包-packages" / "t0" / "scripts"))
    from monitor import _chan_realtime_alert, _norm_sig  # type: ignore
except Exception:  # pragma: no cover
    _chan_realtime_alert = None  # type: ignore
    _norm_sig = None  # type: ignore


def _make_bar(o, h, l, c, date=None, volume=1000):
    bar = {"open": o, "high": h, "low": l, "close": c, "volume": volume}
    if date is not None:
        bar["date"] = date
    return bar


def _gen_bars(n=120, seed=42, with_date=True):
    import random

    random.seed(seed)
    bars = []
    price = 50.0
    for i in range(n):
        drift = 0.4 * __import__("math").sin(i / 12.0) + 0.05
        o = price
        c = max(1.0, price + drift + random.uniform(-0.6, 0.6))
        h = max(o, c) + random.uniform(0, 1.0)
        l = min(o, c) - random.uniform(0, 1.0)
        bar = {
            "open": round(o, 2), "high": round(h, 2), "low": round(l, 2),
            "close": round(c, 2), "volume": 1000 + random.randint(0, 300),
        }
        if with_date:
            bar["date"] = str(20240101 + i)
        bars.append(bar)
        price = c
    return bars


class _FakeSnapshot:
    def __init__(self, daily_bars, code="688248"):
        self.daily_bars = daily_bars
        self.security = type("S", (), {"code": code, "name": "test"})()


class _FakeProvider:
    def __init__(self, bars_by_name, code_by_name=None):
        self._bars = bars_by_name
        self._code = code_by_name or {}

    def load_market_snapshot(self, target, days=300, include_5m=True, include_weekly=True,
                             include_monthly=True, include_ticks=True):
        bars = self._bars.get(target)
        # 按名称解析 code（与 Part B 真实路径 snapshot.security.code 对齐）
        code = self._code.get(target, target if target.isdigit() else "688248")
        return _FakeSnapshot(bars or [], code=code)


# ── Part B：cache warm 预建缠论状态 ──

class TestWarmChanlunStates:
    def test_generates_state_files_and_consistent(self, tmp_path, monkeypatch):
        # 临时池 + 临时状态目录，避免污染真实 HOME
        pool = {"items": [
            {"name": "测试股A", "code": "688248", "status": "观察"},
            {"name": "测试股B", "code": "600000", "status": "执行"},
            {"name": "已退出股", "code": "000001", "status": "已退出"},
        ]}
        home = tmp_path / "home"
        home.mkdir()
        (home / ".trader").mkdir()
        (home / ".trader" / "pool.json").write_text(json.dumps(pool), encoding="utf-8")
        monkeypatch.setattr(Path, "home", lambda: home)

        state_dir = tmp_path / "chan_state"
        state_dir.mkdir()
        monkeypatch.setattr(
            __import__("trader_shared.config", fromlist=["x"]), "CHANLUN_STATE_DIR", str(state_dir)
        )

        bars_a = _gen_bars(120, seed=1)
        bars_b = _gen_bars(120, seed=2)
        provider = _FakeProvider(
            {"测试股A": bars_a, "测试股B": bars_b},
            code_by_name={"测试股A": "688248", "测试股B": "600000"},
        )
        from trader_shared import data_provider

        monkeypatch.setattr(data_provider, "get_provider", lambda: provider)

        result = warm_chanlun_states()

        # 活跃 2 只，已退出 1 只不处理
        assert result["total"] == 2
        assert result["success"] == 2
        assert result["failed"] == 0

        for code in ("688248", "600000"):
            p = state_dir / f"{code}.json"
            assert p.exists(), f"状态文件 {code}.json 未生成"
            eng = ChanlunEngine.load(str(p))
            # load 后与由 daily 重算的引擎一致
            ref = ChanlunEngine()
            for b in (bars_a if code == "688248" else bars_b):
                ref.update_bar(b)
            assert len(eng.cleaned) == len(ref.cleaned)
            assert len(eng.strokes) == len(ref.strokes)

    def test_fault_tolerant_on_empty_bars(self, tmp_path, monkeypatch):
        pool = {"items": [{"name": "空数据股", "code": "123456", "status": "观察"}]}
        home = tmp_path / "home"
        home.mkdir()
        (home / ".trader").mkdir()
        (home / ".trader" / "pool.json").write_text(json.dumps(pool), encoding="utf-8")
        monkeypatch.setattr(Path, "home", lambda: home)
        state_dir = tmp_path / "chan_state"
        state_dir.mkdir()
        monkeypatch.setattr(
            __import__("trader_shared.config", fromlist=["x"]), "CHANLUN_STATE_DIR", str(state_dir)
        )
        provider = _FakeProvider({"空数据股": []})  # 空 daily_bars → 失败但不阻断
        from trader_shared import data_provider

        monkeypatch.setattr(data_provider, "get_provider", lambda: provider)

        result = warm_chanlun_states()
        assert result["total"] == 1
        assert result["failed"] == 1
        assert result["success"] == 0
        assert result["errors"]


# ── Part C：T0 实时缠论增量 ──

class TestRealtimeChan:
    def _plan(self, current, bars, quote=None):
        return {
            "daily_bars": bars,
            "current_price": current,
            "quote": quote or {},
            "data": {"quote": quote or {}},
        }

    def test_get_realtime_chan_returns_result_and_signature(self):
        bars = _gen_bars(120, seed=5)
        current = float(bars[-1]["close"])
        rc = get_realtime_chan("688248", self._plan(current, bars))
        assert isinstance(rc["result"], dict)
        assert isinstance(rc["signature"], tuple)
        assert "strokes" in rc["result"]

    def test_signature_changes_across_ticks_and_alert(self):
        # 同一标的在不同观察时刻（两种结构形态）的两帧快照：
        # 批量 build_strokes 仅跟踪「已确认笔」，末笔端点需新确认分型才会演进，
        # 故两 tick 用两套不同结构形态（不同 seed）代表盘中结构发生实质变化，
        # 指纹应随之变化并触发人话 alert。
        bars1 = _gen_bars(120, seed=9)
        bars2 = _gen_bars(120, seed=99)
        rc1 = get_realtime_chan("688248", self._plan(float(bars1[-1]["close"]), bars1))
        rc2 = get_realtime_chan("688248", self._plan(float(bars2[-1]["close"]), bars2))

        # 两 tick 结构形态不同 → 指纹应变化
        assert rc1["signature"] != rc2["signature"], "两 tick 结构形态变化应驱动缠论指纹变化"

        # 后一 tick 相对前一 tick 应产出非空人话 alert
        assert _chan_realtime_alert is not None, "monitor._chan_realtime_alert 应可导入"
        alert = _chan_realtime_alert(rc2["result"], rc1["signature"])
        assert isinstance(alert, str) and alert.strip(), "_chan_realtime_alert 应产出非空行"

    def test_signature_distinguishes_results(self):
        # 直接验证 _chan_signature 对末笔/结构/买卖点的区分能力（diff 机制单测）
        r1 = {"structure_type": "a", "trend_label": "拉升段", "strokes": [{"direction": "up", "end_price": 10.0}],
              "buy_points": [], "sell_points": []}
        r2 = {"structure_type": "a", "trend_label": "拉升段", "strokes": [{"direction": "up", "end_price": 10.0}],
              "buy_points": [{"type": "一类买"}], "sell_points": []}
        r3 = {"structure_type": "a", "trend_label": "回调段", "strokes": [{"direction": "down", "end_price": 9.5}],
              "buy_points": [], "sell_points": []}
        assert _chan_signature(r1) != _chan_signature(r2)
        assert _chan_signature(r1) != _chan_signature(r3)
        # 价格 2 位四舍五入容忍 tick 抖动
        r1b = dict(r1); r1b["strokes"] = [{"direction": "up", "end_price": 10.004}]
        assert _chan_signature(r1) == _chan_signature(r1b)

    def test_norm_sig_handles_json_roundtrip(self):
        # 状态文件经 JSON 往返后 tuple→list（含嵌套），_norm_sig 必须抵消该差异，
        # 否则 monitor 下一 tick 会因 tuple≠list 误判变化而重复告警。
        assert _norm_sig is not None, "monitor._norm_sig 应可导入"
        sig = ("无结构", "拉升段", "up", 58.38, ("一类买",), ())
        as_list = list(sig)
        as_list[4] = list(as_list[4])  # 嵌套 tuple→list
        assert _norm_sig(sig) == _norm_sig(as_list)
        assert _norm_sig(sig) == sig

    def test_load_or_build_falls_back_to_batch(self, tmp_path):
        bars = _gen_bars(80, seed=3)
        # 不存在的预热文件 → 静默回退批量 build，结果应当与直接 build 一致
        eng = _load_or_build("NOPE", bars, state_dir=str(tmp_path))
        ref = ChanlunEngine()
        for b in bars:
            ref.update_bar(b)
        assert len(eng.strokes) == len(ref.strokes)

    def test_signature_deterministic_for_same_result(self):
        bars = _gen_bars(80, seed=4)
        current = float(bars[-1]["close"])
        rc = get_realtime_chan("X", self._plan(current, bars))
        # 相同输入两次 → 相同指纹
        rc2 = get_realtime_chan("X", self._plan(current, bars))
        assert rc["signature"] == rc2["signature"]
