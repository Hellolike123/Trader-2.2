"""A 合同测例 — fetch_qfq_daily 日线 volume 单位审计（wyckoff-epic-vol-phase-verif-handoff §1 方向 A）。

法源：``docs/plans/wyckoff-epic-vol-phase-verif-handoff.md`` §1（A-M1~A-M4）与 §4 验收（A1~A4）。

⚠️ 实测修正（A-M1「以源码/协议证据为准」条款）：
  handoff 假设「腾讯日线=股、fallback=手」→ fallback ×100 归一到股。
  实测证据（amount 交叉验证 + 腾讯实时抓取）表明 **腾讯日线 volume=手**，与
  sina/mootdx/pytdx3/tushare 全部一致：
    - amount 交叉验证：000001/600519/300750/000858/600036/601318/688248 等缓存日线
      均满足 amount ≈ volume × 100 × close（偏差 <3%），无一满足「股」；
    - 腾讯实时 qfqday（web.ifzq.gtimg.cn，即代码 TENCENT_FQKLINE_URL）：
      601398 08-03 vol=5,128,943 ≈ 缓存（mootdx=手）07-24 3,689,522；
      600519 08-03 vol=36,147 ≈ 缓存 07-31 55,127；000001 08-04 vol=1,221,130 ≈
      缓存 07-31 2,024,978 —— 同量级，证明腾讯=手。
  故本测例断言：**fallback 不 ×100（各源天然同单位=手）**，仅补 vol_unit="lot"
  自描述标记；若按 handoff 字面 ×100，会把 fallback 变股、与腾讯（手）反向制造
  100× 失真。vol_unit 取值按实际单位 "lot"（手）而非 handoff 字面 "share"
  （后者基于「腾讯=股」错误前提）。

离线约束：mock http / fallback 拉取函数；cache_utils.CACHE_DIR 指到 pytest tmp
目录——不触网、不碰真实 ~/.trader/cache。
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import trader_shared.cache_utils as cu
from trader_shared import light_data


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path, monkeypatch):
    """把 cache_utils 的 CACHE_DIR 指到 tmp，隔离真实缓存文件。"""
    cache_dir = tmp_path / "cache"
    monkeypatch.setattr(cu, "CACHE_DIR", cache_dir)
    return cache_dir


@pytest.fixture
def sec():
    return light_data.resolve_security("000001")


@pytest.fixture
def http():
    return MagicMock()


def _make_daily(dates: list[str], vols: list[float] | None = None) -> list[dict]:
    """日线构造行（单位=手；与腾讯/mootdx/sina 协议一致）。"""
    vols = vols or [100.0] * len(dates)
    return [
        {
            "date": d,
            "open": 10.0,
            "high": 11.0,
            "low": 9.0,
            "close": 10.5,
            "volume": v,
        }
        for d, v in zip(dates, vols)
    ]


_DATES = ["2026-07-27", "2026-07-28", "2026-07-29", "2026-07-30", "2026-07-31"]


class _CircuitStub:
    """熔断器桩：恒闭合 + 记数 no-op，隔离真实熔断状态。"""

    is_open = False

    def record_success(self):
        pass

    def record_failure(self):
        pass


@pytest.fixture
def fail_tencent(monkeypatch, http):
    """腾讯主路径恒失败（get_text 抛 OSError），fallback 分支可测。"""
    http.get_text.side_effect = OSError("network down")
    monkeypatch.setattr(light_data, "_circuit_tencent_daily", _CircuitStub())
    return http


class TestDailyFallbackVolumeA:
    """A-M1 / A1：三个 fallback 源（sina/mootdx/pytdx3）**不** ×100，仅补 vol_unit 标记。

    实测修正依据见模块 docstring：各源 volume 单位均为「手」，与腾讯一致。
    """

    def test_a1a_sina_fallback_not_multiplied_and_marked(self, sec, http, monkeypatch, fail_tencent):
        sina_bars = _make_daily(_DATES, [100.0, 100.0, 100.0, 100.0, 84498.17])
        monkeypatch.setattr(light_data, "_fetch_daily_sina", MagicMock(return_value=sina_bars))
        monkeypatch.setattr(light_data, "_fetch_qfq_tdx3", MagicMock(return_value=None))
        monkeypatch.setattr(light_data, "_fetch_qfq_mootdx", MagicMock(return_value=None))

        bars = light_data.fetch_qfq_daily(sec, http, days=30)

        assert bars[-1]["volume"] == pytest.approx(84498.17)  # 不 ×100（=手，与腾讯一致）
        assert all(b.get("vol_unit") == "lot" for b in bars)
        assert bars[0]["data_source"] == "sina"

    def test_a1b_pytdx3_fallback_not_multiplied_and_marked(self, sec, http, monkeypatch, fail_tencent):
        tdx3_bars = _make_daily(_DATES, [100.0, 100.0, 100.0, 100.0, 84498.17])
        monkeypatch.setattr(light_data, "_fetch_daily_sina", MagicMock(return_value=None))
        monkeypatch.setattr(light_data, "_check_pytdx3", MagicMock(return_value=True))
        monkeypatch.setattr(light_data, "_fetch_qfq_tdx3", MagicMock(return_value=tdx3_bars))
        monkeypatch.setattr(light_data, "_fetch_qfq_mootdx", MagicMock(return_value=None))

        bars = light_data.fetch_qfq_daily(sec, http, days=30)

        assert bars[-1]["volume"] == pytest.approx(84498.17)
        assert all(b.get("vol_unit") == "lot" for b in bars)
        assert bars[0]["data_source"] == "pytdx3"

    def test_a1c_mootdx_fallback_not_multiplied_and_marked(self, sec, http, monkeypatch, fail_tencent):
        mootdx_bars = _make_daily(_DATES, [100.0, 100.0, 100.0, 100.0, 84498.17])
        monkeypatch.setattr(light_data, "_fetch_daily_sina", MagicMock(return_value=None))
        monkeypatch.setattr(light_data, "_check_pytdx3", MagicMock(return_value=True))
        monkeypatch.setattr(light_data, "_fetch_qfq_tdx3", MagicMock(return_value=None))
        monkeypatch.setattr(light_data, "_fetch_qfq_mootdx", MagicMock(return_value=mootdx_bars))

        bars = light_data.fetch_qfq_daily(sec, http, days=30)

        assert bars[-1]["volume"] == pytest.approx(84498.17)
        assert all(b.get("vol_unit") == "lot" for b in bars)
        assert bars[0]["data_source"] == "mootdx"


class TestTencentSuccessPathA:
    """A-M2 / A2：腾讯成功路径不 ×100，写缓存前每根 bar 打 vol_unit="lot"。"""

    def _jsonp_payload(self) -> str:
        import datetime as _dt

        # ≥200 根才过 validate_bars 写文件缓存；末根 vol=23456 用于断言不乘
        dates = [
            (_dt.date(2026, 7, 31) - _dt.timedelta(days=209 - i)).strftime("%Y-%m-%d")
            for i in range(210)
        ]
        rows = [
            [d, "10.0", "10.5", "10.6", "9.9", "23456" if d == "2026-07-31" else "100"]
            for d in dates
        ]
        # 腾讯 fqkline 响应为纯 JSON（无 `_var=` 前缀；extract_jsonp 遇 "=" 会切坏）
        return '{"data":{"sz000001":{"qfqday":' + __import__("json").dumps(rows) + "}}}"

    def test_a2_tencent_success_stamps_cache_not_multiplied(self, sec, http, monkeypatch, tmp_path):
        http.get_text.return_value = self._jsonp_payload()
        # 新鲜度判定恒 live → 跳过 URL 缓存（文件缓存写入不受影响，确定性离线）
        monkeypatch.setattr(
            "trader_shared.trading_context.compute_data_freshness",
            lambda d: "live",
        )

        bars = light_data.fetch_qfq_daily(sec, http, days=30)

        # 返回侧：不 ×100，带标记
        assert bars[-1]["volume"] == pytest.approx(23456.0)
        assert all(b.get("vol_unit") == "lot" for b in bars)
        assert bars[0]["data_source"] == "tencent-http"
        # 文件缓存侧：新格式带标记（A2）
        target = cu.daily_bars_cache_target(
            sec.code, provider="tencent", adjust="qfq", market=sec.market
        )
        cached = cu.get_cached(cu.CACHE_DAILY, target, ttl=cu.TTL_BARS_DAY)
        assert cached is not None
        rows = cu.unwrap_bars_payload(cached.data)
        assert rows is not None and len(rows) >= 2
        assert all(r.get("vol_unit") == "lot" for r in rows)
        assert rows[-1]["volume"] == pytest.approx(23456.0)

    def test_a3_legacy_cache_read_unchanged(self, sec, http, monkeypatch):
        """旧缓存（无 vol_unit 标记，恒手单位）同日命中 → 原样返回，不补标、不乘。"""
        dates = [f"2026-01-{d:02d}" for d in range(1, 32)] * 7
        legacy = _make_daily(dates[:210])  # 210 根无标记
        for b in legacy:
            b.pop("vol_unit", None)
        target = cu.daily_bars_cache_target(
            sec.code, provider="tencent", adjust="qfq", market=sec.market
        )
        cu.set_cached(
            cu.CACHE_DAILY,
            target,
            {"fetch_date": cu.cache_calendar_date(), "rows": legacy},
        )

        bars = light_data.fetch_qfq_daily(sec, http, days=300)

        assert len(bars) == 210
        assert all("vol_unit" not in b for b in bars)  # 读取行为不变（A-P2）
        assert bars[-1]["volume"] == pytest.approx(100.0)  # 数值未乘
        http.get_text.assert_not_called()  # 同日缓存短路，未触网


class TestCrossPeriodComparableA:
    """A-M3 / A3：日线（手）与周线聚合路径（=日线逐日求和，手）跨周期量级可比。"""

    def test_a3_daily_lot_comparable_with_weekly_aggregate(self):
        from trader_shared.indicator_math import aggregate_daily_to_weekly

        daily = _make_daily(
            [
                "2026-06-29", "2026-06-30", "2026-07-01", "2026-07-02", "2026-07-03",
                "2026-07-06", "2026-07-07", "2026-07-08", "2026-07-09", "2026-07-10",
            ],
            [100, 100, 100, 100, 100, 200, 200, 200, 200, 200],
        )
        weekly = aggregate_daily_to_weekly(daily)
        # 周线（聚合路径）= 日线逐日求和（手），同一量纲 → 跨周期可直接比较量级
        assert weekly[-1]["volume"] == pytest.approx(1000.0)  # 5×200
        assert weekly[-2]["volume"] == pytest.approx(500.0)  # 5×100
