"""筹码搬家监控器 — 存储 chip_distribution 结果并对比前后变化。

使用:
  from trader_shared.chip_migration_monitor import save_chip_snapshot, check_chip_migration
  save_chip_snapshot("南网科技", chip_result)
  migration = check_chip_migration("南网科技", chip_result)
"""

from __future__ import annotations

import json
import os
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from trader_shared._logging import get_logger

_logger = get_logger(__name__)

_CHIP_HISTORY_PATH = Path(os.path.expanduser("~/.trader/chip_history.json"))

# 搬家警告阈值
_MIGRATION_WARNING_THRESHOLD = 0.40  # 底部峰下降 > 40% → 警告
_MIGRATION_CLEAR_THRESHOLD = 0.50    # 底部峰下降 > 50% → 清仓信号

# 回填天数（前两周 ≈ 10 个交易日）
_BACKFILL_DAYS = 10


def _load_history() -> dict[str, Any]:
    """Load chip history from file."""
    try:
        if _CHIP_HISTORY_PATH.exists():
            return json.loads(_CHIP_HISTORY_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        _logger.debug("Chip history load failed: %s", exc)
    return {}


def _save_history(history: dict[str, Any]) -> None:
    """Save chip history to file atomically."""
    try:
        _CHIP_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = _CHIP_HISTORY_PATH.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
        with tmp.open("rb") as f:
            os.fsync(f.fileno())
        tmp.replace(_CHIP_HISTORY_PATH)
    except OSError as exc:
        _logger.debug("Chip history save failed: %s", exc)


def _build_snapshot(chip_result: dict[str, Any], trade_date: str) -> dict[str, Any] | None:
    """从 chip_distribution 结果构建快照 dict，无 peaks 则返回 None。"""
    peaks = chip_result.get("peaks", [])
    if not peaks:
        return None

    support_peaks = [p for p in peaks if "支撑" in str(p.get("support_level", ""))]
    return {
        "date": trade_date,
        "peaks": [
            {
                "price": p["price"],
                "share_of_total": p["share_of_total"],
                "support_level": p["support_level"],
            }
            for p in support_peaks
        ],
    }


def save_chip_snapshot(
    target: str,
    chip_result: dict[str, Any],
    trade_date: str | None = None,
) -> None:
    """保存筹码分布快照到历史文件。

    Parameters
    ----------
    target : str
        股票名或代码
    chip_result : dict
        calc_chip_distribution() 的返回结果
    trade_date : str | None
        交易日期，默认今天
    """
    today = trade_date or date.today().isoformat()
    snapshot = _build_snapshot(chip_result, today)
    if snapshot is None:
        return

    history = _load_history()
    history[target] = snapshot
    _save_history(history)


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

    # 如果已有昨天的回填数据，跳过
    yesterday = (date.today() - timedelta(days=1)).isoformat()
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

    # 回填前 _BACKFILL_DAYS 个交易日
    backfill_count = 0
    # bars 按时间正序排列，取最后 _BACKFILL_DAYS+60 天的数据用于计算
    total_bars = len(bars)
    for i in range(max(0, total_bars - _BACKFILL_DAYS), total_bars):
        bar = bars[i]
        trade_date = bar.get("date", "")
        if not trade_date:
            continue

        # 用截至当天的数据计算筹码分布
        bars_slice = bars[: i + 1]
        try:
            chip_result = calc_chip_distribution(bars_slice, lookback=60)
        except Exception as exc:
            _logger.debug("Chip calc failed for %s on %s: %s", target, trade_date, exc)
            continue

        _save_backfill_snapshot(history, target, trade_date, chip_result)
        backfill_count += 1

    if backfill_count > 0:
        _save_history(history)
        _logger.debug("Chip history backfilled for %s: %d days", target, backfill_count)

    return backfill_count > 0


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

    # 没有历史数据时尝试回填
    if not prev_snapshot or not prev_snapshot.get("peaks"):
        if bars and len(bars) >= 60:
            backfill_history(target, bars)
            history = _load_history()
            prev_snapshot = history.get(target)

    # 如果还是没有，尝试找昨天的回填数据
    if not prev_snapshot or not prev_snapshot.get("peaks"):
        yesterday = (date.today() - timedelta(days=1)).isoformat()
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

    # 找到历史底部峰（最强支撑）
    prev_support_peaks = [p for p in prev_snapshot["peaks"] if "支撑" in str(p.get("support_level", ""))]
    if not prev_support_peaks:
        return {
            "migration_pct": 0.0,
            "warning_level": "none",
            "warning_text": "",
            "has_history": True,
        }

    # 取历史最强底部峰
    prev_peak = max(prev_support_peaks, key=lambda p: p.get("share_of_total", 0))
    prev_share = prev_peak.get("share_of_total", 0)
    prev_price = prev_peak.get("price", 0)

    if prev_share <= 0:
        return {
            "migration_pct": 0.0,
            "warning_level": "none",
            "warning_text": "",
            "has_history": True,
        }

    # 在当前 peaks 中找价格最接近的支撑峰（用 startswith 匹配"支撑"开头的级别）
    current_support_peaks = [p for p in current_peaks if str(p.get("support_level", "")).startswith("支撑")]
    if not current_support_peaks:
        # 所有支撑峰都消失了 → 100% 搬家
        migration_pct = 100.0
    else:
        # 找价格最接近的峰
        closest = min(current_support_peaks, key=lambda p: abs(p["price"] - prev_price))
        current_share = closest.get("share_of_total", 0)
        # 计算搬家百分比
        if prev_share > current_share:
            migration_pct = round((prev_share - current_share) / prev_share * 100, 1)
        else:
            migration_pct = 0.0

    # 判断警告级别
    migration_ratio = migration_pct / 100.0
    if migration_ratio >= _MIGRATION_CLEAR_THRESHOLD:
        warning_level = "critical"
        warning_text = (
            f"底部筹码峰从 {prev_share:.1f}% 降到 "
            f"{max(0, prev_share - prev_share * migration_ratio):.1f}%"
            f"（-{migration_pct:.0f}%），清仓信号"
        )
    elif migration_ratio >= _MIGRATION_WARNING_THRESHOLD:
        warning_level = "warning"
        warning_text = (
            f"底部筹码峰从 {prev_share:.1f}% 降到 "
            f"{max(0, prev_share - prev_share * migration_ratio):.1f}%"
            f"（-{migration_pct:.0f}%），筹码松动警告"
        )
    else:
        warning_level = "none"
        warning_text = ""

    return {
        "migration_pct": migration_pct,
        "warning_level": warning_level,
        "warning_text": warning_text,
        "has_history": True,
        "prev_date": prev_snapshot.get("date"),
        "prev_share": prev_share,
    }
