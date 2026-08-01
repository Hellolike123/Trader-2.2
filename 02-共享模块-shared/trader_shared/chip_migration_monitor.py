"""筹码搬家监控器 — 存储 chip_distribution 结果并对比前后变化。

使用:
  from trader_shared.chip_migration_monitor import save_chip_snapshot, check_chip_migration
  save_chip_snapshot("南网科技", chip_result)
  migration = check_chip_migration("南网科技", chip_result)
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

from trader_shared._logging import get_logger
from trader_shared.json_atomic import load_json_dict, locked_rmw_json
from trader_shared.trader_paths import path as trader_path

_logger = get_logger(__name__)


def _today_iso() -> str:
    try:
        from trader_shared.cn_time import today_cn
        return today_cn().isoformat()
    except Exception:
        return date.today().isoformat()


def _prev_trading_day_iso(as_of: date | None = None) -> str:
    """上一交易日（非日历 yesterday），供回填键查找。"""
    try:
        from trader_shared.cn_time import today_cn
        from trader_shared.trading_context import _last_trading_day
        d = as_of or today_cn()
        return _last_trading_day(d - timedelta(days=1)).isoformat()
    except Exception:
        base = as_of or date.today()
        return (base - timedelta(days=1)).isoformat()


def _chip_history_path() -> Path:
    """``~/.trader/chip_history.json`` (via trader_paths)."""
    return trader_path("chip_history")


# 搬家警告阈值
_MIGRATION_WARNING_THRESHOLD = 0.40  # 底部峰下降 > 40% → 警告
_MIGRATION_CLEAR_THRESHOLD = 0.50    # 底部峰下降 > 50% → 清仓信号

# 回填天数（前两周 ≈ 10 个交易日）
_BACKFILL_DAYS = 10


def _load_history() -> dict[str, Any]:
    """Load chip history from file（无锁读；写路径须走 locked_rmw）。"""
    return load_json_dict(_chip_history_path())


def _save_history(history: dict[str, Any]) -> None:
    """锁内全量写（调用方应已合并好；并发写请用 locked_rmw mutator）。"""
    try:
        locked_rmw_json(_chip_history_path(), lambda _old: history if isinstance(history, dict) else {})
    except OSError as exc:
        _logger.debug("Chip history save failed: %s", exc)


def _build_snapshot(chip_result: dict[str, Any], trade_date: str) -> dict[str, Any] | None:
    """从 chip_distribution 结果构建快照 dict，无 peaks 则返回 None。"""
    peaks = chip_result.get("peaks", [])
    if not peaks:
        return None

    # 计算 POC（成交量最大的峰）
    poc_price = None
    if peaks:
        max_vol_peak = max(peaks, key=lambda p: p.get("volume", p.get("share_of_total", 0)))
        poc_price = max_vol_peak.get("price")

    return {
        "date": trade_date,
        "poc_price": poc_price,
        "peaks": [
            {
                "price": p["price"],
                "share_of_total": p["share_of_total"],
                "support_level": p["support_level"],
            }
            for p in peaks
        ],
    }


def save_chip_snapshot(
    target: str,
    chip_result: dict[str, Any],
    trade_date: str | None = None,
) -> None:
    """保存筹码分布快照到历史文件（保留每个标的最近5次快照）。

    Parameters
    ----------
    target : str
        股票名或代码
    chip_result : dict
        calc_chip_distribution() 的返回结果
    trade_date : str | None
        交易日期，默认今天
    """
    today = trade_date or _today_iso()
    snapshot = _build_snapshot(chip_result, today)
    if snapshot is None:
        return

    def _mutate(history: dict[str, Any]) -> dict[str, Any]:
        # 保留最近 5 次快照：追加新快照，超过 5 则去重裁旧
        existing: list[dict[str, Any]] = history.get(target, [])
        if not isinstance(existing, list):
            existing = [existing] if isinstance(existing, dict) else []
        if existing and existing[-1].get("date") == today:
            existing[-1] = snapshot
        else:
            existing.append(snapshot)
        if len(existing) > 5:
            existing = existing[-5:]
        history[target] = existing
        return history

    try:
        locked_rmw_json(_chip_history_path(), _mutate)
    except OSError as exc:
        _logger.debug("Chip history save failed: %s", exc)


def _save_backfill_snapshot(
    history: dict[str, Any],
    target: str,
    trade_date: str,
    chip_result: dict[str, Any],
) -> None:
    """将回填的单日快照写入 history dict（不立即落盘）。"""
    snapshot = _build_snapshot(chip_result, trade_date)
    if snapshot is None:
        return

    key = f"{target}_{trade_date}"
    history[key] = snapshot


def backfill_history(
    target: str,
    bars: list[dict[str, Any]],
) -> bool:
    """回填前两周筹码分布历史数据。

    Parameters
    ----------
    target : str
        股票名或代码
    bars : list[dict]
        完整日线 K 线数据（至少 60 根用于筹码计算）

    Returns
    -------
    bool
        True 表示回填成功，False 表示跳过（已有数据或数据不足）
    """
    history = _load_history()

    # 如果已有上一交易日的回填数据，跳过（勿用日历 yesterday：周一会 miss）
    yesterday = _prev_trading_day_iso()
    yesterday_key = f"{target}_{yesterday}"
    if yesterday_key in history:
        _logger.debug("Chip history backfill skipped for %s: yesterday data exists", target)
        return False

    # 数据不足则跳过
    if len(bars) < 60:
        _logger.debug("Chip history backfill skipped for %s: only %d bars", target, len(bars))
        return False

    # 懒加载 chip_distribution 避免循环导入
    try:
        from trader_shared.chip_distribution import calc_chip_distribution
    except ImportError:
        _logger.debug("chip_distribution not available, backfill skipped")
        return False

    # 计算在锁外；合并写入走锁内 RMW（避免长持 flock）
    pending: dict[str, Any] = {}
    backfill_count = 0
    total_bars = len(bars)
    for i in range(max(0, total_bars - _BACKFILL_DAYS), total_bars):
        bar = bars[i]
        trade_date = bar.get("date", "")
        if not trade_date:
            continue

        bars_slice = bars[: i + 1]
        try:
            chip_result = calc_chip_distribution(bars_slice, lookback=60)
        except Exception as exc:
            _logger.debug("Chip calc failed for %s on %s: %s", target, trade_date, exc)
            continue

        _save_backfill_snapshot(pending, target, trade_date, chip_result)
        backfill_count += 1

    if backfill_count > 0:
        def _mutate(store: dict[str, Any]) -> dict[str, Any]:
            store.update(pending)
            return store

        try:
            locked_rmw_json(_chip_history_path(), _mutate)
        except OSError as exc:
            _logger.debug("Chip history backfill save failed: %s", exc)
            return False
        _logger.debug("Chip history backfilled for %s: %d days", target, backfill_count)

    return backfill_count > 0


def _calc_poc_migration(prev: dict[str, Any], curr: dict[str, Any]) -> dict[str, Any] | None:
    """对比前后 POC（Point of Control，成交量最大价位）变化。"""
    prev_poc = prev.get("poc_price") or prev.get("max_volume_price")
    curr_poc = curr.get("poc_price") or curr.get("max_volume_price")
    if prev_poc is None or curr_poc is None:
        # 尝试从 peaks 推算：占比最大的峰的价格
        prev_peaks = prev.get("peaks", [])
        curr_peaks = curr.get("peaks", [])
        if prev_peaks and curr_peaks:
            prev_poc = max(prev_peaks, key=lambda p: p.get("share_of_total", 0)).get("price", 0)
            curr_poc = max(curr_peaks, key=lambda p: p.get("share_of_total", 0)).get("price", 0)
        else:
            return None
    prev_poc = float(prev_poc)
    curr_poc = float(curr_poc)
    if prev_poc <= 0 or curr_poc <= 0:
        return None
    shift_pct = round((curr_poc - prev_poc) / prev_poc * 100, 2)
    return {"prev_poc": prev_poc, "curr_poc": curr_poc, "shift_pct": shift_pct}


def _calc_value_area_migration(prev: dict[str, Any], curr: dict[str, Any]) -> dict[str, Any] | None:
    """对比前后 Value Area（70% 成交量区间）宽窄变化。"""
    prev_va_low = prev.get("value_area_low")
    prev_va_high = prev.get("value_area_high")
    curr_va_low = curr.get("value_area_low")
    curr_va_high = curr.get("value_area_high")
    if not all([prev_va_low, prev_va_high, curr_va_low, curr_va_high]):
        return None
    prev_va_low = float(prev_va_low)
    prev_va_high = float(prev_va_high)
    curr_va_low = float(curr_va_low)
    curr_va_high = float(curr_va_high)
    prev_width = prev_va_high - prev_va_low
    curr_width = curr_va_high - curr_va_low
    if prev_width <= 0 or curr_width <= 0:
        return None
    width_change_pct = round((curr_width - prev_width) / prev_width * 100, 2)
    return {
        "prev_va_low": prev_va_low, "prev_va_high": prev_va_high,
        "curr_va_low": curr_va_low, "curr_va_high": curr_va_high,
        "prev_width": round(prev_width, 2), "curr_width": round(curr_width, 2),
        "width_change_pct": width_change_pct,
    }


def check_chip_migration(
    target: str,
    current_chip_result: dict[str, Any],
    bars: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """对比当前筹码分布与历史快照，返回搬家百分比和警告级别。

    Parameters
    ----------
    target : str
        股票名或代码
    current_chip_result : dict
        calc_chip_distribution() 的返回结果
    bars : list[dict] | None
        日线 K 线数据，用于回填历史（可选）

    Returns
    -------
    dict with keys:
        migration_pct : float        底部峰搬家百分比（0-100）
        warning_level : str          "none" / "warning" / "critical"
        warning_text : str           可读警告文本
        has_history : bool           是否有历史数据可对比
    """
    history = _load_history()
    prev_snapshot = history.get(target)
    # 兼容旧格式（单快照）和新格式（列表）
    if isinstance(prev_snapshot, list):
        prev_snapshot = prev_snapshot[-1] if prev_snapshot else None

    # 没有历史数据时尝试回填
    if not prev_snapshot or not prev_snapshot.get("peaks"):
        if bars and len(bars) >= 60:
            backfill_history(target, bars)
            history = _load_history()
            prev_snapshot = history.get(target)

    # 如果还是没有，尝试找上一交易日的回填数据
    if not prev_snapshot or not prev_snapshot.get("peaks"):
        yesterday = _prev_trading_day_iso()
        yesterday_key = f"{target}_{yesterday}"
        prev_snapshot = history.get(yesterday_key)

    # 如果还是没有，找最近的回填数据
    if not prev_snapshot or not prev_snapshot.get("peaks"):
        # 按日期倒序找最近的回填数据
        for key in sorted(history.keys(), reverse=True):
            if key.startswith(f"{target}_") and history[key].get("peaks"):
                prev_snapshot = history[key]
                break

    if not prev_snapshot or not prev_snapshot.get("peaks"):
        return {
            "migration_pct": 0.0,
            "warning_level": "none",
            "warning_text": "",
            "has_history": False,
        }

    current_peaks = current_chip_result.get("peaks", [])
    if not current_peaks:
        return {
            "migration_pct": 0.0,
            "warning_level": "none",
            "warning_text": "当前无筹码数据",
            "has_history": True,
        }

    # 找到历史底部峰（最强支撑）和历史上方峰（最强阻力）
    prev_support_peaks = [p for p in prev_snapshot["peaks"] if "支撑" in str(p.get("support_level", ""))]
    prev_resistance_peaks = [p for p in prev_snapshot["peaks"] if "阻力" in str(p.get("support_level", ""))]

    prev_support_share = 0.0
    prev_support_price = 0.0
    if prev_support_peaks:
        # 统一用最大占比选取（与当前峰匹配逻辑一致）
        prev_support_peak = max(prev_support_peaks, key=lambda p: p.get("share_of_total", 0))
        prev_support_share = prev_support_peak.get("share_of_total", 0)
        prev_support_price = prev_support_peak.get("price", 0)

    prev_resistance_share = 0.0
    prev_resistance_price = 0.0
    if prev_resistance_peaks:
        prev_resistance_peak = max(prev_resistance_peaks, key=lambda p: p.get("share_of_total", 0))
        prev_resistance_share = prev_resistance_peak.get("share_of_total", 0)
        prev_resistance_price = prev_resistance_peak.get("price", 0)

    # 如果都没有，直接返回
    if prev_support_share <= 0 and prev_resistance_share <= 0:
        return {
            "migration_pct": 0.0,
            "warning_level": "none",
            "warning_text": "",
            "has_history": True,
        }

    current_support_share = 0.0
    current_support_peaks = [p for p in current_peaks if "支撑" in str(p.get("support_level", ""))]
    
    migration_pct = 0.0
    if prev_support_share > 0:
        if not current_support_peaks:
            migration_pct = 100.0
        else:
            # 统一用最大占比选取（与历史峰选取逻辑一致）
            strongest_supp = max(current_support_peaks, key=lambda p: p.get("share_of_total", 0))
            current_support_share = strongest_supp.get("share_of_total", 0)
            if prev_support_share > current_support_share:
                migration_pct = round((prev_support_share - current_support_share) / prev_support_share * 100, 1)

    current_resistance_share = 0.0
    current_resistance_peaks = [p for p in current_peaks if "阻力" in str(p.get("support_level", ""))]
    if prev_resistance_share > 0 and current_resistance_peaks:
        strongest_res = max(current_resistance_peaks, key=lambda p: p.get("share_of_total", 0))
        current_resistance_share = strongest_res.get("share_of_total", 0)

    support_diff = round(current_support_share - prev_support_share, 2) if prev_support_share > 0 else 0.0
    resistance_diff = round(current_resistance_share - prev_resistance_share, 2) if prev_resistance_share > 0 else 0.0

    warning_text = ""
    warning_level = "none"

    # 判断警告级别和对比逻辑
    migration_ratio = migration_pct / 100.0
    if support_diff <= -0.5 and resistance_diff >= 0.5:
        warning_level = "critical" if migration_ratio >= _MIGRATION_CLEAR_THRESHOLD else "warning"
        warning_text = f"底部支撑减少 {abs(support_diff):.1f}%，上方阻力增加 {resistance_diff:.1f}% → 筹码在搬家，主力在出货"
    elif support_diff >= 0.5 and resistance_diff <= -0.5:
        warning_level = "none"
        warning_text = f"上方阻力减少 {abs(resistance_diff):.1f}%，底部支撑增加 {support_diff:.1f}% → 主力在吸筹"
    elif support_diff <= -0.5:
        warning_level = "critical" if migration_ratio >= _MIGRATION_CLEAR_THRESHOLD else "warning"
        warning_text = f"底部支撑减少 {abs(support_diff):.1f}%（-{migration_pct:.0f}%） → 筹码松动警告"
    elif resistance_diff >= 0.5:
        warning_level = "warning"
        warning_text = f"上方阻力增加 {resistance_diff:.1f}% → 抛压加重"
    else:
        warning_text = "底部筹码基本稳定，无明显搬家"

    return {
        "migration_pct": migration_pct,
        "warning_level": warning_level,
        "warning_text": warning_text,
        "has_history": True,
        "prev_date": prev_snapshot.get("date"),
        "support_migration": {
            "prev_price": prev_support_price,
            "prev_share": prev_support_share,
            "curr_share": current_support_share,
            "diff": support_diff,
        } if prev_support_share > 0 else None,
        "resistance_migration": {
            "prev_price": prev_resistance_price,
            "prev_share": prev_resistance_share,
            "curr_share": current_resistance_share,
            "diff": resistance_diff,
        } if prev_resistance_share > 0 else None,
        # POC 控制点 & Value Area 趋势
        "poc_migration": _calc_poc_migration(prev_snapshot, current_chip_result),
        "value_area_migration": _calc_value_area_migration(prev_snapshot, current_chip_result),
    }


# ── 筹码搬家趋势输出（最近5次底部峰变化趋势）────────────────────────

def get_chip_migration_trend(target: str) -> dict[str, Any]:
    """返回最近 5 次筹码快照的底部峰变化趋势。

    用于在复盘报告中展示「底部筹码峰是否持续下降」的趋势线索。

    Returns
    -------
    dict with keys:
        trend_text : str        趋势描述文本
        bottom_peak_pcts : list 最近各快照的底部峰占比列表
        dates : list            对应日期
        direction : str         "declining" / "stable" / "rising" / "insufficient_data"
    """
    history = _load_history()
    snapshots = history.get(target)
    if isinstance(snapshots, dict):
        snapshots = [snapshots]
    if not isinstance(snapshots, list) or len(snapshots) < 2:
        return {"trend_text": "数据不足", "bottom_peak_pcts": [], "dates": [],
                "direction": "insufficient_data"}

    pcts: list[float] = []
    dates: list[str] = []
    for snap in snapshots[-5:]:
        peaks = snap.get("peaks", [])
        if not peaks:
            continue
        # 底部峰 = 价格最低的峰
        bottom_peak = min(peaks, key=lambda p: p.get("price", 0))
        pcts.append(bottom_peak.get("share_of_total", 0))
        dates.append(snap.get("date", "?"))

    if len(pcts) < 2:
        return {"trend_text": "数据不足", "bottom_peak_pcts": pcts, "dates": dates,
                "direction": "insufficient_data"}

    first = pcts[0]
    last = pcts[-1]
    change = last - first

    if abs(change) < 2:
        direction = "stable"
        trend_text = f"底部峰稳定在 ~{last:.1f}%"
    elif change < 0:
        pct_drop = abs(change) / first * 100 if first else 0
        if pct_drop > 50:
            direction = "declining"
            trend_text = f"⚠️ 底部峰从 {first:.1f}% 降至 {last:.1f}%（降 {pct_drop:.0f}%），主力或已出货"
        elif pct_drop > 30:
            direction = "declining"
            trend_text = f"⚡ 底部峰下降：{first:.1f}% → {last:.1f}%"
        else:
            direction = "declining"
            trend_text = f"底部峰缓降：{first:.1f}% → {last:.1f}%"
    else:
        direction = "rising"
        trend_text = f"底部峰上升：{first:.1f}% → {last:.1f}%（承接增强）"

    return {
        "trend_text": trend_text,
        "bottom_peak_pcts": pcts,
        "dates": dates,
        "direction": direction,
    }
