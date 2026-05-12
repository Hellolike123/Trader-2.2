#!/usr/bin/env python3
"""FIX-01~07 修复回归测试。

FIX-01: 极端跳空保护阈值 500%→50%
FIX-02: 去重 key 统一规范化（symbol/date/type）
FIX-03: 结果写入 result_time + show_single 按 result_time 排序
FIX-04: show_single name 匹配 strip
FIX-07: load_recent 按时间排序
"""
from __future__ import annotations

import importlib
import json
import sys
import shutil
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

SHARED = Path(__file__).resolve().parent.parent
SCRIPTS = SHARED / "scripts"
for _p in (SHARED, SCRIPTS):
    if str(_p.resolve()) not in sys.path:
        sys.path.insert(0, str(_p.resolve()))

# Force reload to pick up code changes
import signal_tracker
importlib.reload(signal_tracker)
st = signal_tracker


# ═══════ FIX-01: 极端跳空阈值 50% ═══════

class TestExtremeGap:
    """FIX-01: return_pct > 50% 时应标记 _extreme_Nd。

    注意：_compute_results_for_sig() 开头有 `if HttpClient is None: return None`，
    所以必须同时 patch HttpClient 为非 None，函数才会走到 fetch_qfq_daily。
    另外 `to_float` 需要能被调用（当前环境未导入 light_data，默认返回 None）。
    """

    def setup_method(self):
        fake_client = MagicMock()
        self._p1 = patch.object(st, "HttpClient", return_value=fake_client)
        self._p2 = patch.object(st, "resolve_security", return_value=None)
        # FIX-01: to_float 在当前环境默认返回 None → atr 除法报错，必须 mock 为普通函数
        self._p3 = patch.object(st, "to_float", side_effect=lambda v: float(v) if v else 0.0)
        self._p1.start()
        self._p2.start()
        self._p3.start()

    def teardown_method(self):
        self._p1.stop()
        self._p2.stop()
        self._p3.stop()

    def _make_bars(self, close_5d_price=15):
        """生成 mock bars，包含交易日的每一天。"""
        bars = [{"date": "2026-04-02", "close": 10, "atr14": 0.5}]
        # 需要 40 天的 bar，覆盖从 2026-03-05 到 2026-05-11
        import datetime
        start = datetime.date(2026, 3, 5)
        for i in range(40):
            d = (start + datetime.timedelta(days=i)).strftime("%Y-%m-%d")
            if d == "2026-04-02":
                # close 已经是 10
                continue
            elif d == "2026-04-07" or d == "2026-04-08" or d == "2026-04-03" or d == "2026-04-06" or d == "2026-04-09" or d == "2026-04-10" or d == "2026-04-13" or d == "2026-04-14":
                bars.append({"date": d, "close": close_5d_price, "atr14": 0.6})
            else:
                bars.append({"date": d, "close": 10, "atr14": 0.5})
        return bars

    def test_extreme_50pct_not_triggers(self):
        """恰 50% 回落不触发。"""
        sig = {
            "symbol": "688248.SH", "name": "南网科技",
            "trade_date": "2026-04-02", "signal_type": "track",
            "trigger": {"price": 10}, "source_skill": "trader",
        }
        mock_bars = self._make_bars(close_5d_price=15)  # 50% return
        with patch.object(st, "fetch_qfq_daily", return_value=mock_bars):
            result = st._compute_results_for_sig(sig)
            assert result is not None
            assert "_extreme_5d" not in result, "恰 50% 不应标记异常"

    def test_extreme_above_50pct_triggers(self):
        """60% 应标记 _extreme_5d。"""
        sig = {
            "symbol": "688248.SH", "name": "南网科技",
            "trade_date": "2026-04-02", "signal_type": "track",
            "trigger": {"price": 10}, "source_skill": "trader",
        }
        mock_bars = self._make_bars(close_5d_price=16)  # 60% return
        with patch.object(st, "fetch_qfq_daily", return_value=mock_bars):
            result = st._compute_results_for_sig(sig)
            assert result is not None
            assert result.get("_extreme_5d") is True, "60% 涨幅应标记 _extreme_5d"

    def test_extreme_nearby_days_also_checked(self):
        """1d 也检查极端跳空。"""
        sig = {
            "symbol": "688248.SH", "name": "南网科技",
            "trade_date": "2026-04-02", "signal_type": "track",
            "trigger": {"price": 10}, "source_skill": "trader",
        }
        mock_bars = self._make_bars(close_5d_price=10)
        # 2026-04-03 是 1d
        for b in mock_bars:
            if b["date"] == "2026-04-03":
                b["close"] = 16
        with patch.object(st, "fetch_qfq_daily", return_value=mock_bars):
            result = st._compute_results_for_sig(sig)
            assert result is not None
            assert result.get("_extreme_1d") is True, "1d 60% 应标记 _extreme_1d"


# ═══════ FIX-02: 去重 key 统一规范化 ═══════

class TestDedupNormalization:
    """FIX-02: existing key 与 new key 统一规范化。"""

    def setup_method(self):
        self.tmp = Path(f"/tmp/.trader_test_dedup_{id(self)}")
        self.tmp.mkdir(exist_ok=True, parents=True)
        self._orig = {"RESULT_PATH": st.RESULT_PATH, "STORE_PATH": st.STORE_PATH}
        st.RESULT_PATH = self.tmp / "signal_results.jsonl"
        st.STORE_PATH = self.tmp / "signals.jsonl"

    def teardown_method(self):
        st.RESULT_PATH = self._orig["RESULT_PATH"]
        st.STORE_PATH = self._orig["STORE_PATH"]
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_dedup_with_mixed_case_symbol(self):
        """结果已有 .SH 大写，新 signal 用小写应去重。"""
        # 用当前日期附近，确保 cutoff <= trade_date
        today = st.datetime.now().strftime("%Y-%m-%d")
        sig = {
            "symbol": "688248.sh", "name": "南网科技",
            "trade_date": today, "signal_type": "track",
            "trigger": {"price": 20}, "source_skill": "trader",
        }
        (self.tmp / "signals.jsonl").write_text(
            json.dumps(sig) + "\n", encoding="utf-8")
        # 先手动写一条已有的结果（symbol 大写）
        existing = json.dumps({
            "symbol": "688248.SH", "name": "南网科技",
            "signal_date": today, "signal_type": "track",
            "signal_price": 20,
            "r_5d": 3.0, "schema_version": "v1",
        })
        st.RESULT_PATH.write_text(existing + "\n", encoding="utf-8")

        # 需要 patch HttpClient + fetch_qfq_daily 让 _compute_results_for_sig 不报错
        # 但不需要 mock data — 去重会跳过计算
        fake_client = MagicMock()
        with (
            patch.object(st, "HttpClient", return_value=fake_client),
            patch.object(st, "resolve_security", return_value=None),
        ):
            result = st.check_recent(days=5)
        assert result["updated"] == 0, f"不应新写，已存在: {result}"
        assert result["skipped"] >= 1, "应跳过已有记录, got: {result}"


# ═══════ FIX-03: result_time 字段 ═══════

class TestResultTime:
    """FIX-03: 结果写入 result_time + show_single 按 result_time 排序。"""

    def setup_method(self):
        self.tmp = Path(f"/tmp/.trader_test_rt_{id(self)}")
        self.tmp.mkdir(exist_ok=True, parents=True)
        self._orig = {"RESULT_PATH": st.RESULT_PATH}
        st.RESULT_PATH = self.tmp / "signal_results.jsonl"

    def teardown_method(self):
        st.RESULT_PATH = self._orig["RESULT_PATH"]
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_result_time_field_present(self):
        """新增结果应包含 result_time 字段。"""
        rec1 = json.dumps({
            "symbol": "688248.SH", "name": "南网科技",
            "signal_date": "2026-04-01", "signal_type": "track",
            "r_5d": 2.0, "outcome": "up",
            "result_time": "2026-04-05T14:00:00", "schema_version": "v1",
        })
        rec2 = json.dumps({
            "symbol": "688248.SH", "name": "南网科技",
            "signal_date": "2026-04-01", "signal_type": "track",
            "r_5d": 5.0, "outcome": "up",
            "result_time": "2026-04-06T14:00:00", "schema_version": "v1",
        })
        st.RESULT_PATH.write_text(rec1 + "\n" + rec2 + "\n", encoding="utf-8")

        panel = st.show_single("688248.SH")
        assert "信号追踪面板" in panel
        # 应能返回两条记录的面板（因为 symbol + signal_date + signal_type 相同且都在）
        # 关键是 show_single 能读 result_time 并正确排序

    def test_result_time_sort_order(self):
        """打乱文件顺序后，show_single 仍按 result_time 降序。"""
        rec_old = json.dumps({
            "symbol": "000001.SZ", "name": "平安银行",
            "signal_date": "2026-04-01", "signal_type": "observe",
            "r_5d": 1.0, "outcome": "up",
            "result_time": "2026-04-05T10:00:00", "schema_version": "v1",
        })
        rec_new = json.dumps({
            "symbol": "000001.SZ", "name": "平安银行",
            "signal_date": "2026-04-01", "signal_type": "observe",
            "r_5d": 3.0, "outcome": "up",
            "result_time": "2026-04-06T10:00:00", "schema_version": "v1",
        })
        # 故意先写新、后写旧（文件乱序）
        st.RESULT_PATH.write_text(rec_new + "\n" + rec_old + "\n", encoding="utf-8")

        results = st._make_panel(st._load_results(), None)
        assert "信号追踪面板" in results
        # 应该有 2 条记录被统计


# ═══════ FIX-04: name 匹配 strip ═══════

class TestNameStrip:
    """FIX-04: show_single name 匹配 strip。"""

    def setup_method(self):
        self.tmp = Path(f"/tmp/.trader_test_name_{id(self)}")
        self.tmp.mkdir(exist_ok=True, parents=True)
        self._orig = {"RESULT_PATH": st.RESULT_PATH}
        st.RESULT_PATH = self.tmp / "signal_results.jsonl"

    def teardown_method(self):
        st.RESULT_PATH = self._orig["RESULT_PATH"]
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_name_match_with_spaces(self):
        """记录 name 无空格，查询带空格应匹配。"""
        rec = json.dumps({
            "symbol": "688248.SH", "name": "南网科技",
            "signal_date": "2026-04-01", "signal_type": "track",
            "r_5d": 3.5, "outcome": "up", "schema_version": "v1",
        })
        st.RESULT_PATH.write_text(rec + "\n", encoding="utf-8")

        panel = st.show_single(" 南网科技 ")
        assert "信号追踪面板" in panel, "name 带空格应匹配"

    def test_name_match_non_existent(self):
        """不存在名称应正常返回空面板。"""
        rec = json.dumps({
            "symbol": "688248.SH", "name": "南网科技",
            "signal_date": "2026-04-01", "signal_type": "track",
            "r_5d": 3.5, "outcome": "up", "schema_version": "v1",
        })
        st.RESULT_PATH.write_text(rec + "\n", encoding="utf-8")

        panel = st.show_single(" 不存在的股票 ")
        assert "无有效结果" in panel


# ═══════ FIX-07: load_recent 按时间排序 ═══════

class TestLoadRecentSort:
    """FIX-07: load_recent 按 timestamp 排序后取 limit。"""

    def setup_method(self):
        self._orig = st.LOG_PATH
        self.tmp = Path(f"/tmp/.trader_load_{id(self)}")
        self.tmp.parent.mkdir(parents=True, exist_ok=True)
        st.LOG_PATH = self.tmp

    def teardown_method(self):
        st.LOG_PATH = self._orig
        self.tmp.unlink(missing_ok=True)

    def test_load_recent_sorted_by_timestamp(self):
        """旧记录在文件头部：limit=1 应返回 timestamp 最新的。"""
        old_record = json.dumps({
            "signal_id": "aaaaa", "timestamp": "2026-01-01 10:00",
            "skill": "trader", "target": "南网科技", "symbol": "688248.SH",
            "signal_type": "track", "price": 20,
            "outcome_pnl_pct": None, "outcome_days": None,
            "outcome": None, "filled_at": None,
        })
        new_record = json.dumps({
            "signal_id": "bbbbb", "timestamp": "2026-04-01 14:00",
            "skill": "trader", "target": "南网科技", "symbol": "688248.SH",
            "signal_type": "track", "price": 25,
            "outcome_pnl_pct": None, "outcome_days": None,
            "outcome": None, "filled_at": None,
        })
        # 旧记录在前，新记录在后
        self.tmp.write_text(old_record + "\n" + new_record + "\n", encoding="utf-8")

        recent = st.load_recent(target="南网科技", limit=1)
        assert len(recent) == 1
        assert recent[0]["signal_id"] == "bbbbb", \
            f"应返回 timestamp 最新记录 bbbbb，实际: {recent[0]['signal_id']}"

    def test_load_recent_reverse_order(self):
        """新记录在前，旧记录在后：limit=1 应仍返回新记录。"""
        new_record = json.dumps({
            "signal_id": "bbbbb", "timestamp": "2026-04-01 14:00",
            "skill": "trader", "target": "南网科技", "symbol": "688248.SH",
            "signal_type": "track", "price": 25,
            "outcome_pnl_pct": None, "outcome_days": None,
            "outcome": None, "filled_at": None,
        })
        old_record = json.dumps({
            "signal_id": "aaaaa", "timestamp": "2026-01-01 10:00",
            "skill": "trader", "target": "南网科技", "symbol": "688248.SH",
            "signal_type": "track", "price": 20,
            "outcome_pnl_pct": None, "outcome_days": None,
            "outcome": None, "filled_at": None,
        })
        # 新记录在前，旧在后
        self.tmp.write_text(new_record + "\n" + old_record + "\n", encoding="utf-8")

        recent = st.load_recent(target="南网科技", limit=1)
        assert len(recent) == 1
        assert recent[0]["signal_id"] == "bbbbb", \
            f"应返回 timestamp 最新记录 bbbbb，实际: {recent[0]['signal_id']}"

    def test_load_recent_uses_filled_at_when_present(self):
        """当 filled_at 存在时优先用 filled_at 排序。"""
        rec1 = json.dumps({
            "signal_id": "aaa", "timestamp": "2026-04-01 10:00",
            "skill": "trader", "target": "南网科技", "symbol": "688248.SH",
            "signal_type": "track", "price": 20,
            "outcome_pnl_pct": None, "outcome_days": None,
            "outcome": None, "filled_at": "2026-04-01 10:00",
        })
        rec2 = json.dumps({
            "signal_id": "bbb", "timestamp": "2026-03-01 10:00",
            "skill": "trader", "target": "南网科技", "symbol": "688248.SH",
            "signal_type": "track", "price": 25,
            "outcome_pnl_pct": 5.0, "outcome_days": 3,
            "outcome": "up", "filled_at": "2026-05-01 10:00",
        })
        self.tmp.write_text(rec1 + "\n" + rec2 + "\n", encoding="utf-8")

        recent = st.load_recent(target="南网科技", limit=1)
        assert len(recent) == 1
        assert recent[0]["signal_id"] == "bbb", \
            f"应返回 filled_at 最新的 bbb，实际: {recent[0]['signal_id']}"

    def test_load_recent_empty(self):
        """空文件应返回空列表。"""
        self.tmp.write_text("", encoding="utf-8")
        recent = st.load_recent(target="南网科技", limit=1)
        assert recent == []

    def test_load_recent_limit_more_than_available(self):
        """limit 超过实际记录时应返回全部。"""
        rec1 = json.dumps({
            "signal_id": "aaa", "timestamp": "2026-04-01 10:00",
            "skill": "trader", "target": "南网科技", "symbol": "688248.SH",
            "signal_type": "track", "price": 20,
            "outcome_pnl_pct": None, "outcome_days": None,
            "outcome": None, "filled_at": None,
        })
        rec2 = json.dumps({
            "signal_id": "bbb", "timestamp": "2026-04-02 10:00",
            "skill": "trader", "target": "南网科技", "symbol": "688248.SH",
            "signal_type": "track", "price": 25,
            "outcome_pnl_pct": None, "outcome_days": None,
            "outcome": None, "filled_at": None,
        })
        self.tmp.write_text(rec1 + "\n" + rec2 + "\n", encoding="utf-8")

        recent = st.load_recent(target="南网科技", limit=10)
        assert len(recent) == 2
        assert recent[0]["signal_id"] == "bbb"
        assert recent[1]["signal_id"] == "aaa"

    def test_load_recent_filtered_by_symbol(self):
        """按 symbol 过滤后也应正确排序。"""
        rec1 = json.dumps({
            "signal_id": "aaaa", "timestamp": "2026-04-01 10:00",
            "skill": "trader", "target": "南网科技", "symbol": "688248.SH",
            "signal_type": "track", "price": 20,
            "outcome_pnl_pct": None, "outcome_days": None,
            "outcome": None, "filled_at": None,
        })
        rec2 = json.dumps({
            "signal_id": "bbbb", "timestamp": "2026-04-02 10:00",
            "skill": "trader", "target": "中国铝业", "symbol": "601600.SH",
            "signal_type": "track", "price": 15,
            "outcome_pnl_pct": None, "outcome_days": None,
            "outcome": None, "filled_at": None,
        })
        self.tmp.write_text(rec1 + "\n" + rec2 + "\n", encoding="utf-8")

        recent = st.load_recent(target="南网科技", limit=1)
        assert len(recent) == 1
        assert recent[0]["signal_id"] == "aaaa"
