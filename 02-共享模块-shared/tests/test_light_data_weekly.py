"""D/E 合同测例 — fetch_weekly 周线新鲜度(D) + volume 单位归一(E)。

法源：``docs/plans/wyckoff-sos-epic-fde-handoff.md`` §1（D-M1~D-M4 / E-M1~E-M5）
与 §4 验收表（D1/D2/E1/E2/E3）。

离线约束：mock ``fetch_qfq_daily`` / ``_fetch_mins_fallback`` / ``_fetch_mins_mootdx``，
并把 ``cache_utils.CACHE_DIR`` 指到 pytest tmp 目录——不触网、不碰真实 ~/.trader/cache。
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


# 2026-07/08 的周五（周线间距，median gap=7 天 ≥ 3 → weekly_bars_look_like_weekly=True）
_FRIDAYS = ["2026-07-03", "2026-07-10", "2026-07-17", "2026-07-24", "2026-07-31"]
# 周一起（周一 = 2026-08-03，周二 = 2026-08-04）
_MONDAYS = ["2026-07-06", "2026-07-13", "2026-07-20", "2026-07-27", "2026-08-03"]


def _make_weekly(dates: list[str], last_vol: float = 100.0) -> list[dict]:
    bars = []
    for i, d in enumerate(dates):
        bars.append(
            {
                "date": d,
                "open": 10.0 + i,
                "high": 11.0 + i,
                "low": 9.0 + i,
                "close": 10.5 + i,
                "volume": last_vol if i == len(dates) - 1 else 100.0,
            }
        )
    return bars


def _make_daily(dates: list[str], vols: list[float] | None = None) -> list[dict]:
    """日线（腾讯单位=股）；未给 vols 时逐日 100.0。"""
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


_DAILY_WEEK1 = ["2026-06-29", "2026-06-30", "2026-07-01", "2026-07-02", "2026-07-03"]
_DAILY_WEEK2 = ["2026-07-06", "2026-07-07", "2026-07-08", "2026-07-09", "2026-07-10"]
_DAILY_WEEK3 = ["2026-07-13", "2026-07-14", "2026-07-15", "2026-07-16", "2026-07-17"]
_DAILY_WEEK4 = ["2026-07-20", "2026-07-21", "2026-07-22", "2026-07-23", "2026-07-24"]
_DAILY_WEEK5 = ["2026-07-27", "2026-07-28", "2026-07-29", "2026-07-30", "2026-07-31"]
_DAILY_WEEK6 = ["2026-08-03", "2026-08-04"]  # 周一、周二（周线最后 bar=周二）


@pytest.fixture
def sec():
    return light_data.resolve_security("600036")


@pytest.fixture
def http():
    return MagicMock()


def _seed_weekly_cache(target: str, bars: list[dict], *, tagged: bool) -> None:
    """写周线缓存（fetch_date=今天，同日命中 get_day_scoped_bars）。"""
    rows = [dict(b) for b in bars]
    if tagged:
        for b in rows:
            b["vol_unit"] = "share"
    cu.set_cached(
        cu.CACHE_WEEKLY, target, {"fetch_date": cu.cache_calendar_date(), "rows": rows}
    )


class TestWeeklyFreshnessD:
    """D-M1~D-M4 / D1 / D2：周线缓存滞后于日线 → 重聚合覆盖；相等 → 复用。"""

    def test_d1_weekly_lags_daily_reaggregates(self, sec, http, monkeypatch):
        """缓存周线最后 bar=周一(08-03)、日线最后 bar=周二(08-04) → 重聚后周线最后 bar=周二。"""
        _seed_weekly_cache(
            "600036_SH", _make_weekly(_MONDAYS, last_vol=500.0), tagged=True
        )
        daily = (
            _make_daily(_DAILY_WEEK1)
            + _make_daily(_DAILY_WEEK2)
            + _make_daily(_DAILY_WEEK3)
            + _make_daily(_DAILY_WEEK4)
            + _make_daily(_DAILY_WEEK5)
            + _make_daily(_DAILY_WEEK6)
        )
        mock_daily = MagicMock(return_value=daily)
        monkeypatch.setattr(light_data, "fetch_qfq_daily", mock_daily)
        monkeypatch.setattr(light_data, "_fetch_mins_fallback", MagicMock(return_value=None))
        monkeypatch.setattr(light_data, "_fetch_mins_mootdx", MagicMock(return_value=None))

        bars = light_data.fetch_weekly(sec, http, datalen=8)

        assert bars[-1]["date"] == "2026-08-04"  # 重聚合含盘中新 bar
        assert bars[-1]["vol_unit"] == "share"
        # 缓存已覆盖写回（fetch_date=今天，rows 最新 bar=周二）
        cached = cu.get_cached(cu.CACHE_WEEKLY, "600036_SH")
        assert cached is not None
        rows = cached.data["rows"]
        assert rows[-1]["date"] == "2026-08-04"
        # fresh 日线复用聚合，无二次拉取（fresh 一次即闭环）
        assert mock_daily.call_count == 1

    def test_d2_weekend_no_new_data_reuses_cache(self, sec, http, monkeypatch):
        """日线最后 bar=周五(07-31)、缓存=周五(07-31) → 复用缓存，不重聚合。"""
        seeded = _make_weekly(_FRIDAYS, last_vol=500.0)
        _seed_weekly_cache("600036_SH", seeded, tagged=True)
        mock_daily = MagicMock(return_value=_make_daily(_DAILY_WEEK1 + _DAILY_WEEK2 + _DAILY_WEEK3 + _DAILY_WEEK4 + _DAILY_WEEK5))
        monkeypatch.setattr(light_data, "fetch_qfq_daily", mock_daily)
        monkeypatch.setattr(light_data, "_fetch_mins_fallback", MagicMock(return_value=None))
        monkeypatch.setattr(light_data, "_fetch_mins_mootdx", MagicMock(return_value=None))

        bars = light_data.fetch_weekly(sec, http, datalen=8)

        assert [b["date"] for b in bars] == _FRIDAYS  # 缓存原样复用
        assert bars[-1]["volume"] == 500.0
        # 只走新鲜度闸一次（无滞后 → 不调 _from_daily）
        assert mock_daily.call_count == 1

    def test_d3_prewarmed_same_day_cache_reaggregates_via_fresh(self, sec, http, monkeypatch):
        """凌晨预热场景（查 Agent Delta 1）：日线同日缓存只剩周一（非 fresh 短路返回），
        fresh=True 强制触网取到周二 → 周线仍重聚合，不再残留滞后。"""
        _seed_weekly_cache("600036_SH", _make_weekly(_MONDAYS, last_vol=500.0), tagged=True)
        daily_monday = _make_daily(
            _DAILY_WEEK1 + _DAILY_WEEK2 + _DAILY_WEEK3 + _DAILY_WEEK4 + _DAILY_WEEK5
            + ["2026-08-03"]  # 凌晨缓存：本周只聚合到周一
        )
        daily_tuesday = _make_daily(_DAILY_WEEK1 + _DAILY_WEEK2 + _DAILY_WEEK3 + _DAILY_WEEK4 + _DAILY_WEEK5 + _DAILY_WEEK6)

        def fake_daily(sec_, http_, days=300, *, fresh=False):
            return daily_tuesday if fresh else daily_monday

        mock_daily = MagicMock(side_effect=fake_daily)
        monkeypatch.setattr(light_data, "fetch_qfq_daily", mock_daily)
        monkeypatch.setattr(light_data, "_fetch_mins_fallback", MagicMock(return_value=None))
        monkeypatch.setattr(light_data, "_fetch_mins_mootdx", MagicMock(return_value=None))

        bars = light_data.fetch_weekly(sec, http, datalen=8)

        # fresh 拉取生效（凌晨缓存不复用）→ 周线重聚合含周二
        assert bars[-1]["date"] == "2026-08-04"
        assert bars[-1]["vol_unit"] == "share"
        assert any(c.kwargs.get("fresh") for c in mock_daily.call_args_list), (
            "D 闸必须以 fresh=True 触网取盘中最新日线"
        )
        cached = cu.get_cached(cu.CACHE_WEEKLY, "600036_SH")
        assert cached is not None
        assert cached.data["rows"][-1]["date"] == "2026-08-04"


class TestWeeklyVolumeUnitE:
    """E-M1~E-M5 / E1 / E2 / E3：sina/mootdx 周线 ×100 归一到股；聚合路径不乘；旧缓存强制回源。"""

    def test_e1_sina_weekly_volume_x100_and_marker(self, sec, http, monkeypatch):
        """sina 构造行 volume=84498.17（手）→ ×100 = 8449817.0（股），每根 bar 带 vol_unit。"""
        # 旧格式缓存（无 vol_unit 标记）→ 触发强制回源
        _seed_weekly_cache("600036_SH", _make_weekly(_FRIDAYS, last_vol=84498.17), tagged=False)
        sina_bars = _make_weekly(_FRIDAYS, last_vol=84498.17)
        mock_sina = MagicMock(return_value=sina_bars)
        monkeypatch.setattr(light_data, "_fetch_mins_fallback", mock_sina)
        monkeypatch.setattr(light_data, "_fetch_mins_mootdx", MagicMock(return_value=None))
        # 日线最后 bar=周五（与 sina 周线一致）→ 新鲜度闸不复聚
        monkeypatch.setattr(
            light_data,
            "fetch_qfq_daily",
            MagicMock(return_value=_make_daily(_DAILY_WEEK1 + _DAILY_WEEK2 + _DAILY_WEEK3 + _DAILY_WEEK4 + _DAILY_WEEK5)),
        )

        bars = light_data.fetch_weekly(sec, http, datalen=8)

        assert mock_sina.called  # 旧缓存无标记 → 强制回源
        assert bars[-1]["volume"] == 84498.17 * 100 == pytest.approx(8449817.0)
        assert all(b.get("vol_unit") == "share" for b in bars)
        # 缓存已重写为带标记的新格式
        cached = cu.get_cached(cu.CACHE_WEEKLY, "600036_SH")
        assert cached is not None
        rows = cached.data["rows"]
        assert rows[0].get("vol_unit") == "share"
        assert rows[-1]["volume"] == pytest.approx(8449817.0)

    def test_e1b_mootdx_weekly_volume_x100_and_marker(self, sec, http, monkeypatch):
        """mootdx 周线（查 Agent SUGGESTED 2）：volume=手 → ×100 归一到股，带 vol_unit 标记。"""
        _seed_weekly_cache("600036_SH", _make_weekly(_FRIDAYS, last_vol=84498.17), tagged=False)
        monkeypatch.setattr(light_data, "_fetch_mins_fallback", MagicMock(return_value=None))
        mock_mootdx = MagicMock(return_value=_make_weekly(_FRIDAYS, last_vol=84498.17))
        monkeypatch.setattr(light_data, "_fetch_mins_mootdx", mock_mootdx)
        # 日线最后 bar=周五（与周线一致）→ 新鲜度闸不复聚
        monkeypatch.setattr(
            light_data,
            "fetch_qfq_daily",
            MagicMock(return_value=_make_daily(_DAILY_WEEK1 + _DAILY_WEEK2 + _DAILY_WEEK3 + _DAILY_WEEK4 + _DAILY_WEEK5)),
        )

        bars = light_data.fetch_weekly(sec, http, datalen=8)

        assert mock_mootdx.called  # sina 空 → mootdx 分支生效
        assert bars[-1]["volume"] == pytest.approx(8449817.0)
        assert all(b.get("vol_unit") == "share" for b in bars)
        cached = cu.get_cached(cu.CACHE_WEEKLY, "600036_SH")
        assert cached.data["rows"][-1]["volume"] == pytest.approx(8449817.0)

    def test_e2_aggregate_path_not_multiplied(self, sec, http, monkeypatch):
        """聚合路径（腾讯日线=股）不 ×100：周线 volume=日线逐日求和。"""
        _seed_weekly_cache("600036_SH", _make_weekly(_FRIDAYS), tagged=False)
        monkeypatch.setattr(light_data, "_fetch_mins_fallback", MagicMock(return_value=None))
        monkeypatch.setattr(light_data, "_fetch_mins_mootdx", MagicMock(return_value=None))
        # 最后一周量能 100+200+300+400+500=1500（股），其余周 500
        daily = (
            _make_daily(_DAILY_WEEK1, [100, 100, 100, 100, 100])
            + _make_daily(_DAILY_WEEK2, [100, 100, 100, 100, 100])
            + _make_daily(_DAILY_WEEK3, [100, 100, 100, 100, 100])
            + _make_daily(_DAILY_WEEK4, [100, 100, 100, 100, 100])
            + _make_daily(_DAILY_WEEK5, [100, 200, 300, 400, 500])
        )
        monkeypatch.setattr(light_data, "fetch_qfq_daily", MagicMock(return_value=daily))

        bars = light_data.fetch_weekly(sec, http, datalen=8)

        assert bars[-1]["date"] == "2026-07-31"
        assert bars[-1]["volume"] == 1500.0  # 原值求和，未 ×100
        assert bars[-2]["volume"] == 500.0
        assert all(b.get("vol_unit") == "share" for b in bars)

    def test_e3_tagged_cache_not_refetched(self, sec, http, monkeypatch):
        """新格式缓存（首根 bar 带 vol_unit="share"）→ 不触发回源。"""
        seeded = _make_weekly(_FRIDAYS, last_vol=500.0)
        _seed_weekly_cache("600036_SH", seeded, tagged=True)
        mock_sina = MagicMock(return_value=_make_weekly(_FRIDAYS, last_vol=1.0))
        monkeypatch.setattr(light_data, "_fetch_mins_fallback", mock_sina)
        monkeypatch.setattr(light_data, "_fetch_mins_mootdx", MagicMock(return_value=None))
        monkeypatch.setattr(
            light_data,
            "fetch_qfq_daily",
            MagicMock(return_value=_make_daily(_DAILY_WEEK1 + _DAILY_WEEK2 + _DAILY_WEEK3 + _DAILY_WEEK4 + _DAILY_WEEK5)),
        )

        bars = light_data.fetch_weekly(sec, http, datalen=8)

        assert not mock_sina.called  # 带标记缓存直接复用，不强制回源
        assert bars[-1]["volume"] == 500.0
