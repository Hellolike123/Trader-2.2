#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from t0_config import LOOKBACK_DAYS

try:
    import trader_shared
except ImportError:
    _d = Path(__file__).resolve().parent
    for _ in range(8):
        if (_d / "trader_shared").is_dir():
            if str(_d) not in sys.path:
                sys.path.insert(0, str(_d))
            import trader_shared
            break
        _d = _d.parent
    else:
        raise

from trader_shared.data_provider import get_provider
from trader_shared.stage_positioning import compute_exit_plan
from trader_shared.tick_cache import save_tick_cache
from price_point_engine import build_price_point_model
from t0_core import (
    build_t0_event_signal,
    build_t0_signals,
    normalize_t0_data_status,
    numeric_or_none,
    observation_valid,
    observation_value,
    pct_text,
    price,
    render_markdown,
    review_lines,
    segment_avg_volume,
    side_status,
    summarize_intraday_segment,
)

try:
    from trader_shared import get_market_level, get_market_note, add_warning
    _SHARED_OK = True
except ImportError:
    import warnings
    warnings.warn(
        "[t0] shared module not available — market status will be unavailable.",
        stacklevel=2,
    )
    _SHARED_OK = False

    def get_market_level() -> str: return ""
    def get_market_note() -> str: return ""
    def add_warning(msg: str, related_stock: str = "") -> None: pass

CONTRACT_VERSION = "t0_price_point_v2"


def build_plan(target: str) -> dict[str, Any]:
    from concurrent.futures import ThreadPoolExecutor

    provider = get_provider()
    sec = provider.resolve_security(target)
    # 5 个数据请求互相独立，并行抓取（串行总耗时≈各请求之和≈0.77s，
    # 并行后≈最慢一个≈0.24s，盘中每个 monitor 循环都能省 0.5s）。
    with ThreadPoolExecutor(max_workers=5) as ex:
        f_quote = ex.submit(provider.fetch_quote, sec)
        f_daily = ex.submit(provider.fetch_qfq_daily, sec, days=LOOKBACK_DAYS)
        f_5m = ex.submit(provider.fetch_5m, sec, datalen=96)
        f_15m = ex.submit(provider.fetch_15m, sec, datalen=60)
        f_30m = ex.submit(provider.fetch_30m, sec, datalen=60)
        # quote/daily 是必需的，立即取（失败抛异常）
        quote = f_quote.result()
        daily = f_daily.result()
        # 分钟线可选，失败降级为空列表
        try:
            bars_5m = f_5m.result()
        except Exception:
            bars_5m = []
        try:
            bars_15m = f_15m.result()
        except Exception:
            bars_15m = []
        try:
            bars_30m = f_30m.result()
        except Exception:
            bars_30m = []
    _cp = quote.get("current_price")
    current = _cp if _cp is not None else (daily[-1].get("close") if daily else None)
    if current is None:
        raise RuntimeError("current price unavailable")
    report_data = {
        "quote": quote,
        "daily_bars": daily,
        "kline_5m": bars_5m,
        "kline_15m": bars_15m,
        "kline_30m": bars_30m,
        "current_price": float(current),
        "tick_data": [],
        "order_book": quote.get("order_book"),
    }
    
    # 被动触发避险控制：当现价靠近低吸或高抛关注价 1.5% 以内时，才触发物理 Tick 盯盘抓取
    temp_model = build_price_point_model(report_data)
    buy_focus = temp_model.get("buy", {}).get("observation_price")
    sell_focus = temp_model.get("sell", {}).get("observation_price")
    near_focus = False
    current_val = float(current)
    if buy_focus and abs(current_val - buy_focus) / buy_focus <= 0.015:
        near_focus = True
    if sell_focus and abs(current_val - sell_focus) / sell_focus <= 0.015:
        near_focus = True
        
    if near_focus:
        try:
            ticks = provider.fetch_ticks(sec, count=500)
            report_data["tick_data"] = ticks
            save_tick_cache(sec.ts_code, ticks, trade_date=quote.get("trade_date"))
            import warnings
            warnings.warn(f"🎯 [PassiveTickTrigger] 现价 {current_val:.2f} 靠近关注价，被动激活物理 Tick 大单验证！")
        except Exception as e:
            warnings.warn(f"[t0] tick fetch failed: {e}")
    # T0-1 fix: 传入 structure_result 让 T0 使用 trader 的支撑/阻力分析
    # 如果有 trader 的分析报告数据，提取其结构分析结果
    structure_result = None
    if isinstance(report_data.get("structure"), dict):
        structure_result = report_data["structure"]
    elif isinstance(report_data.get("structure_result"), dict):
        structure_result = report_data["structure_result"]

    # 5 分钟级实时缠论（提前到 model 构建前，供共振检查使用）
    try:
        from trader_shared.realtime_chan import get_realtime_chan_5m
        rc5 = get_realtime_chan_5m(
            target,
            bars_5m,
            current_price=float(current),
        )
        report_data["chan_5m"] = rc5.get("result") or {}
    except Exception:
        report_data["chan_5m"] = {}

    model = build_price_point_model(report_data, structure_result=structure_result)
    buy_display_status = side_status(model["buy"])
    sell_display_status = side_status(model["sell"])
    buy_display_obs = observation_value(model["buy"], "以下")
    sell_display_obs = observation_value(model["sell"], "附近")
    result = {
        "target": target,
        "name": quote.get("name") or sec.name,
        "symbol": quote.get("symbol") or sec.ts_code,
        "analysis_time": f"{quote.get('trade_date')} {quote.get('trade_time') or ''}".strip(),
        "current_price": round(float(current), 2),
        "current_change_pct": quote.get("current_change_pct"),
        "data_status": model["data_status"],
        "today_action": model["today_action"],
        "max_move": model["max_move"],
        "buy": model["buy"],
        "sell": model["sell"],
        "buy_display_status": buy_display_status,
        "sell_display_status": sell_display_status,
        "buy_display_obs": buy_display_obs,
        "sell_display_obs": sell_display_obs,
        "position_score": model["position_score"],
        "volume_score": model["volume_score"],
        "amplitude_pct": model.get("amplitude_pct"),
        "space_state": model.get("space_state"),
        "volume_ratio": model.get("volume_ratio"),
        "vwap": model.get("vwap"),
        "ict_signal": model.get("ict_signal") or {},
        "atr_info": model.get("atr_info") or {},
        "resonance": model.get("resonance") or {},
        "order_book": quote.get("order_book"),
        "data": report_data,
        "model": model,
    }
    # 分批止盈计划（用当前价作为参考买入价）
    buy_price = numeric_or_none(model["buy"].get("execution_price")) or current
    stop_price = numeric_or_none(model["buy"].get("invalid_price")) or 0
    sell_price = numeric_or_none(model["sell"].get("observation_price"))
    # 威科夫分析（用于实时信号提醒和止盈计划）
    try:
        from trader_shared.wyckoff_core import wyckoff_analysis
        wyck_result = {"wyckoff": wyckoff_analysis(daily, symbol=quote.get("symbol") or "")}
        result["wyckoff"] = wyck_result.get("wyckoff", {})
    except Exception:
        wyck_result = {}
        result["wyckoff"] = {}

    # 取融合层或报告中的阶段，避免硬编码"主升"导致衰退期仍激进
    _stage = result.get("major_stage") or result.get("stage") or "蓄势"
    result["exit_plan"] = compute_exit_plan(
        entry_price=float(buy_price),
        stop_price=float(stop_price),
        resistance_price=float(sell_price) if sell_price and sell_price > buy_price else None,
        current_stage=_stage,
        bars=daily,
        wyckoff_result=wyck_result,
    )

    # 5m 缠论：已提前到 report_data 构建阶段，这里直接复制到 result
    result["chan_5m"] = report_data.get("chan_5m") or {}

    # 筹码搬家监控
    try:
        from trader_shared.chip_distribution import calc_chip_distribution
        from trader_shared.chip_migration_monitor import save_chip_snapshot, check_chip_migration
        chip_dist = calc_chip_distribution(daily, lookback=60)
        name = quote.get("name") or sec.name
        result["chip_migration"] = check_chip_migration(name, chip_dist, bars=daily)
        save_chip_snapshot(name, chip_dist, trade_date=quote.get("trade_date"))
    except Exception:
        result["chip_migration"] = {"migration_pct": 0, "warning_level": "none", "warning_text": "", "has_history": False}

    return result


def current_action_text(plan: dict[str, Any]) -> str:
    if side_status(plan["buy"]) == "可执行":
        return "低吸"
    if side_status(plan["sell"]) == "可执行":
        return "高抛"
    return "不动"


def reminder_level(plan: dict[str, Any]) -> str:
    buy_state = side_status(plan["buy"])
    sell_state = side_status(plan["sell"])
    if "可执行" in {buy_state, sell_state}:
        if plan.get("max_move") == "底仓的 20%-30%" and str(plan.get("data_status")) == "fresh":
            return "可执行"
        return "轻仓做"
    if {buy_state, sell_state} & {"已错过", "被阻断"}:
        return "别犯错"
    return "无"


def buy_status_line(buy: dict[str, Any]) -> str:
    state = side_status(buy)
    if state == "可执行":
        return f"买入：可执行，{price(buy['execution_price'])}附近，最高不超过{price(buy['acceptable_price'])}。"
    if state == "已错过":
        return f"买入：已错过，当前价高于{price(buy.get('acceptable_price'))}，不追。"
    if state == "被阻断":
        return f"买入：被阻断，{'、'.join(buy.get('blocked_reasons') or ['强阻断'])}。"
    if state == "数据不足":
        return "买入：数据不足，不能生成执行价。"
    if observation_valid(buy):
        return f"买入：未触发，等{price(buy['observation_price'])}以下5m止跌。"
    return "买入：未触发，暂无有效观察价。"


def sell_status_line(sell: dict[str, Any]) -> str:
    state = side_status(sell)
    if state == "可执行":
        return f"卖出：可执行，{price(sell['execution_price'])}附近，最低不低于{price(sell['acceptable_price'])}。"
    if state == "已错过":
        return f"卖出：已错过，当前价低于{price(sell.get('acceptable_price'))}，不砸。"
    if state == "被阻断":
        return f"卖出：被阻断，{'、'.join(sell.get('blocked_reasons') or ['强阻断'])}。"
    if state == "数据不足":
        return "卖出：数据不足，不能生成执行价。"
    if observation_valid(sell):
        return f"卖出：未触发，等{price(sell['observation_price'])}附近冲高失败。"
    return "卖出：未触发，暂无有效观察价。"


def intraday_story_lines(plan: dict[str, Any]) -> list[str]:
    bars = ((plan.get("data") or {}).get("kline_5m_completed") or [])[-30:]
    if len(bars) < 6:
        return ["走势：5分钟数据不足，只看执行卡，不做额外复盘。"]
    first_count = min(5, max(2, len(bars) // 4))
    recent_count = min(5, max(2, len(bars) // 4))
    first = bars[:first_count]
    recent = bars[-recent_count:]
    middle = bars[first_count:-recent_count]
    lines = [summarize_intraday_segment("开盘段", first)]
    prev_avg = segment_avg_volume(first)
    if middle:
        lines.append(summarize_intraday_segment("中段", middle, prev_avg))
        prev_avg = segment_avg_volume(middle)
    lines.append(summarize_intraday_segment("最近", recent, prev_avg))
    return lines[:3]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a lightweight A-share intraday T0 card.")
    parser.add_argument("--target", required=True, help="Stock name or code, e.g. 南网科技 or 688248")
    parser.add_argument("--output", choices=["markdown", "json", "signal-json"], default="markdown")
    parser.add_argument("--scale", help=argparse.SUPPRESS)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        plan = build_plan(args.target)
    except Exception as exc:
        print(f"T0数据获取失败：{exc}", file=sys.stderr)
        return 1
    if args.output == "json":
        print(json.dumps({**plan, "signals": build_t0_signals(plan)}, ensure_ascii=False, indent=2, default=str))
    elif args.output == "signal-json":
        print(json.dumps(build_t0_signals(plan), ensure_ascii=False, indent=2, default=str))
    else:
        print(render_markdown(plan))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
