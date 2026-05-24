#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from config import LOOKBACK_DAYS

ROOT = Path(__file__).resolve().parents[3]
SHARED_MARKET = ROOT / "02-共享模块-shared" / "01-行情数据-market-data"
SHARED_SCRIPTS = ROOT / "02-共享模块-shared" / "scripts"
SHARED_ROOT = ROOT / "02-共享模块-shared"
TRADER_SHARED = ROOT / "02-共享模块-shared" / "trader_shared"
CONTRACTS = ROOT / "02-共享模块-shared" / "03-输出校验-contracts"
for _p in (SHARED_MARKET, SHARED_SCRIPTS, SHARED_ROOT, CONTRACTS, TRADER_SHARED):
    if _p.exists() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from trader_shared.data_provider import get_provider
from price_point_engine import build_price_point_model
from signal_contract import assert_valid_signal
from t0_core import (
    build_t0_event_signal,
    build_t0_signals,
    observation_valid,
    observation_value,
    normalize_t0_data_status,
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
        "[t0-trader] shared module not available — market status will be unavailable.",
        stacklevel=2,
    )
    _SHARED_OK = False

    def get_market_level() -> str: return ""
    def get_market_note() -> str: return ""
    def add_warning(msg: str, related_stock: str = "") -> None: pass

CONTRACT_VERSION = "t0_price_point_v2"


def build_plan(target: str) -> dict[str, Any]:
    provider = get_provider()
    sec = provider.resolve_security(target)
    quote = provider.fetch_quote(sec)
    daily = provider.fetch_qfq_daily(sec, days=LOOKBACK_DAYS)
    bars_5m = provider.fetch_5m(sec, datalen=60)
    bars_15m = provider.fetch_15m(sec, datalen=60)
    bars_30m = provider.fetch_30m(sec, datalen=60)
    current = quote.get("current_price") or daily[-1].get("close")
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
            import warnings
            warnings.warn(f"🎯 [PassiveTickTrigger] 现价 {current_val:.2f} 靠近关注价，被动激活物理 Tick 大单验证！")
        except Exception:
            pass
    # T0-1 fix: 传入 structure_result 让 T0 使用 trader 的支撑/阻力分析
    # 如果有 trader 的分析报告数据，提取其结构分析结果
    structure_result = None
    if isinstance(report_data.get("structure"), dict):
        structure_result = report_data["structure"]
    elif isinstance(report_data.get("structure_result"), dict):
        structure_result = report_data["structure_result"]
    model = build_price_point_model(report_data, structure_result=structure_result)
    buy_display_status = side_status(model["buy"])
    sell_display_status = side_status(model["sell"])
    buy_display_obs = observation_value(model["buy"], "以下")
    sell_display_obs = observation_value(model["sell"], "附近")
    return {
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
        "order_book": quote.get("order_book"),
        "data": report_data,
        "model": model,
    }


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
