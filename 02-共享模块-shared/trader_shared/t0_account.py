"""T0 账户层纯函数：成本计算、费后门槛、模式决策、持仓管理。

所有函数纯计算，无副作用，无网络请求。
数据存储在 ~/.trader/position.json（持仓）和 ~/.trader/t0_ledger.jsonl（台账）。
路径经 ``trader_paths`` 解析（可用 ``TRADER_ROOT`` 覆盖根目录）。

Holdings SSOT（``holdings.json``）：``load_position`` / ``save_position`` 优先读写
成本与股数；本 release **双写** position.json 以保持向后兼容（legacy 暂不删除）。
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from trader_shared.trader_paths import path as trader_path


# ── 默认配置（费率 SSOT：trader_shared.config）────────────────────────────
try:
    from trader_shared.config import T0_COMMISSION_RATE, T0_STAMP_TAX_RATE
    DEFAULT_FEE_RATE = T0_COMMISSION_RATE          # 佣金单边万1
    DEFAULT_STAMP_TAX_RATE = T0_STAMP_TAX_RATE      # 印花千1（仅卖）
except Exception:
    DEFAULT_FEE_RATE = 0.0001
    DEFAULT_STAMP_TAX_RATE = 0.001
DEFAULT_MIN_EDGE_PCT = 0.8       # 费后最小净空间 %
DEFAULT_DAY_LOSS_PCT = 1.0       # 当日 T 亏损占市值上限则停
DEFAULT_MAX_T_COUNT = 5          # 当日 T 操作次数上限


# Module attrs for monkeypatch / t0_ledger import; defaults from trader_paths registry.
POSITION_FILE = trader_path("position")
LEDGER_FILE = trader_path("t0_ledger")


# ── 持仓管理 ──────────────────────────────────────────────────────────────
def _load_position_file() -> dict[str, Any]:
    """读取整份 position.json（经 DataManager 读锁）。"""
    try:
        from trader_shared.data_manager import DataManager

        data = DataManager.load_state("position", {"positions": {}})
        if not isinstance(data, dict):
            return {"positions": {}}
        data.setdefault("positions", {})
        return data
    except Exception:
        if not POSITION_FILE.exists():
            return {"positions": {}}
        try:
            data = json.loads(POSITION_FILE.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return {"positions": {}}
            data.setdefault("positions", {})
            return data
        except Exception:
            return {"positions": {}}


def _holding_as_t0_pos(symbol: str) -> dict[str, Any] | None:
    """Map holdings SSOT record → T0 position dict (avg_cost / total_shares)."""
    try:
        from trader_shared.holdings import get_holding

        hit = get_holding(symbol)
    except Exception:
        return None
    if not isinstance(hit, dict):
        return None
    try:
        cost = float(hit.get("cost") or 0)
    except (TypeError, ValueError):
        cost = 0.0
    try:
        shares = int(hit.get("shares") or 0)
    except (TypeError, ValueError):
        shares = 0
    if cost <= 0 and shares <= 0:
        return None
    return {
        "avg_cost": cost,
        "total_shares": shares,
        "name": str(hit.get("name") or ""),
        "updated_at": str(hit.get("updated_at") or ""),
        "source": "holdings",
    }


def _dual_write_holdings(symbol: str, pos: dict[str, Any]) -> None:
    try:
        from trader_shared.holdings import clear_holding, upsert_holding

        cost = float(pos.get("avg_cost") or pos.get("cost") or 0)
        shares = int(pos.get("total_shares") or pos.get("shares") or 0)
        if cost <= 0 and shares <= 0:
            clear_holding(symbol)
            return
        upsert_holding(
            symbol,
            cost=cost,
            shares=shares,
            name=str(pos.get("name") or ""),
            source="t0",
        )
    except Exception:
        pass


def load_position(symbol: str) -> dict[str, Any] | None:
    """读取指定标的的持仓信息（优先 holdings SSOT，否则 position.json）。"""
    hit = _holding_as_t0_pos(symbol)
    if hit is not None:
        legacy = (_load_position_file().get("positions") or {}).get(symbol)
        if isinstance(legacy, dict):
            return {**legacy, **hit}
        return hit
    positions = _load_position_file().get("positions", {})
    return positions.get(symbol)


def save_position(symbol: str, pos: dict[str, Any]) -> None:
    """保存持仓：双写 holdings SSOT + position.json（DataManager 锁内 RMW）。"""
    from trader_shared.data_manager import DataManager

    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    payload = {**pos, "updated_at": stamp}

    def _mutate(data: dict[str, Any]) -> None:
        if not isinstance(data.get("positions"), dict):
            data["positions"] = {}
        data["positions"][symbol] = payload

    DataManager.update_state("position", _mutate)
    _dual_write_holdings(symbol, payload)


def list_positions() -> dict[str, dict[str, Any]]:
    """读取所有持仓（legacy position.json keys + holdings SSOT overlay）。"""
    out: dict[str, dict[str, Any]] = {}
    for sym, rec in (_load_position_file().get("positions") or {}).items():
        if isinstance(rec, dict):
            out[str(sym)] = rec
    try:
        from trader_shared.holdings import list_holdings

        for sym, _rec in list_holdings().items():
            mapped = _holding_as_t0_pos(sym)
            if mapped is None:
                continue
            bare = str(sym).split(".")[0]
            placed = False
            for k in list(out.keys()):
                if k == sym or str(k).split(".")[0] == bare:
                    base = out[k] if isinstance(out.get(k), dict) else {}
                    out[k] = {**base, **mapped}
                    placed = True
                    break
            if not placed:
                out[sym] = mapped
    except Exception:
        pass
    return out


# ── 费用计算 ──────────────────────────────────────────────────────────────
def calc_trade_cost(price: float, shares: int, side: str = "buy",
                    fee_rate: float = DEFAULT_FEE_RATE,
                    stamp_tax_rate: float = DEFAULT_STAMP_TAX_RATE) -> float:
    """计算单笔交易费用（元）。side: 'buy' 或 'sell'。"""
    amount = price * shares
    fee = max(amount * fee_rate, 5.0)  # 佣金最低 5 元
    tax = amount * stamp_tax_rate if side == "sell" else 0.0
    return round(fee + tax, 2)


def calc_round_trip_cost(buy_price: float, sell_price: float, shares: int,
                         fee_rate: float = DEFAULT_FEE_RATE,
                         stamp_tax_rate: float = DEFAULT_STAMP_TAX_RATE) -> float:
    """计算一次完整 T（先卖后买或先买后卖）的总费用。"""
    buy_cost = calc_trade_cost(buy_price, shares, "buy", fee_rate, stamp_tax_rate)
    sell_cost = calc_trade_cost(sell_price, shares, "sell", fee_rate, stamp_tax_rate)
    return round(buy_cost + sell_cost, 2)


def calc_net_edge(sell_price: float, buy_price: float, shares: int,
                  fee_rate: float = DEFAULT_FEE_RATE,
                  stamp_tax_rate: float = DEFAULT_STAMP_TAX_RATE) -> float:
    """计算费后净空间（元）。正值=有利可图。"""
    gross = (sell_price - buy_price) * shares
    cost = calc_round_trip_cost(buy_price, sell_price, shares, fee_rate, stamp_tax_rate)
    return round(gross - cost, 2)


def calc_net_edge_pct(sell_price: float, buy_price: float,
                      fee_rate: float = DEFAULT_FEE_RATE,
                      stamp_tax_rate: float = DEFAULT_STAMP_TAX_RATE) -> float:
    """计算费后净空间百分比。"""
    if buy_price <= 0:
        return 0.0
    shares = 100  # 基准 100 股
    net = calc_net_edge(sell_price, buy_price, shares, fee_rate, stamp_tax_rate)
    return round(net / (buy_price * shares) * 100, 3)


# ── 成本计算 ──────────────────────────────────────────────────────────────
def calc_new_cost(avg_cost: float, total_shares: int,
                  sell_price: float, buy_price: float, t_shares: int) -> float:
    """正 T 后的新均价。

    公式: 新成本 = (C×Q - Ps×q + Pb×q) / Q
    C: 原成本, Q: 总股数, Ps: 卖出价, Pb: 买入价, q: T 股数
    """
    if total_shares <= 0:
        return avg_cost
    new_cost = (avg_cost * total_shares - sell_price * t_shares + buy_price * t_shares) / total_shares
    return round(new_cost, 4)


def calc_cost_reduction(avg_cost: float, new_cost: float) -> dict[str, Any]:
    """计算成本降低幅度。"""
    if avg_cost <= 0:
        return {"reduction_pct": 0.0, "reduction_abs": 0.0, "text": "无成本信息"}
    reduction = avg_cost - new_cost
    pct = reduction / avg_cost * 100
    return {
        "reduction_pct": round(pct, 3),
        "reduction_abs": round(reduction, 4),
        "text": f"成本降低 {pct:.2f}%（{avg_cost:.2f} → {new_cost:.2f}）" if reduction > 0 else "成本未降低",
    }


# ── 模式决策 ──────────────────────────────────────────────────────────────
def decide_t_mode(position: dict[str, Any] | None,
                  current_price: float | None = None) -> dict[str, Any]:
    """根据持仓信息决定 T 模式和行为约束。

    Returns:
        {
            "mode": "cost_cut" | "grid" | "reduce" | "none",
            "allow_reverse_t": bool,    # 是否允许倒 T
            "allow_buyback": bool,      # 高抛后是否允许买回
            "max_t_shares": int,        # 单次最大 T 股数
            "max_t_pct": float,         # 单次最大 T 占底仓比例
            "reason": str,
        }
    """
    if not position:
        return {
            "mode": "none", "allow_reverse_t": False, "allow_buyback": True,
            "max_t_shares": 0, "max_t_pct": 0.0,
            "reason": "无持仓信息，无法做 T",
        }

    avg_cost = float(position.get("avg_cost", 0))
    total_shares = int(position.get("total_shares", 0))
    has_cash = bool(position.get("has_cash", False))
    force_mode = position.get("force_mode", "")

    # 浮亏计算
    float_pnl_pct = 0.0
    if avg_cost > 0 and current_price:
        float_pnl_pct = (current_price - avg_cost) / avg_cost * 100

    # 强制模式
    if force_mode in ("cost_cut", "grid", "reduce"):
        mode = force_mode
    elif avg_cost > 0 and current_price and current_price < avg_cost * 0.9:
        mode = "cost_cut"  # 浮亏超 10% 自动降本模式
    else:
        mode = "grid"

    # 倒 T 控制
    allow_reverse_t = has_cash and mode != "cost_cut"
    if float_pnl_pct < -20:
        allow_reverse_t = False  # 深套禁倒 T

    # 股数控制
    max_t_pct = 0.15 if mode == "cost_cut" else 0.30
    if float_pnl_pct < -20:
        max_t_pct = min(max_t_pct, 0.10)  # 深套压仓
    max_t_shares = max(int(total_shares * max_t_pct), 0)

    return {
        "mode": mode,
        "allow_reverse_t": allow_reverse_t,
        "allow_buyback": True,
        "max_t_shares": max_t_shares,
        "max_t_pct": round(max_t_pct, 2),
        "float_pnl_pct": round(float_pnl_pct, 2),
        "reason": f"模式={mode}, 浮亏{float_pnl_pct:.1f}%, 单次上限{max_t_pct*100:.0f}%",
    }


def is_worth_t(sell_price: float, buy_price: float, min_edge_pct: float = DEFAULT_MIN_EDGE_PCT) -> dict[str, Any]:
    """判断费后是否值得做 T。"""
    net_pct = calc_net_edge_pct(sell_price, buy_price)
    worth = net_pct >= min_edge_pct
    return {
        "worth": worth,
        "net_pct": net_pct,
        "min_edge_pct": min_edge_pct,
        "reason": f"费后净空间 {net_pct:.2f}%，{'≥' if worth else '<'} 门槛 {min_edge_pct}%",
    }


# ── 日损停机 ──────────────────────────────────────────────────────────────
def check_day_loss(t_day_pnl: float, market_value: float,
                   day_loss_pct: float = DEFAULT_DAY_LOSS_PCT) -> dict[str, Any]:
    """检查当日 T 盈亏是否触发停机。"""
    if market_value <= 0:
        return {"stopped": False, "reason": "无市值信息"}
    loss_pct = abs(t_day_pnl) / market_value * 100 if t_day_pnl < 0 else 0.0
    stopped = loss_pct >= day_loss_pct
    return {
        "stopped": stopped,
        "day_pnl": round(t_day_pnl, 2),
        "loss_pct": round(loss_pct, 3),
        "threshold_pct": day_loss_pct,
        "reason": f"当日 T 亏损 {loss_pct:.2f}%，{'达' if stopped else '未达'}停机线 {day_loss_pct}%",
    }


def check_t_frequency(t_count_today: int, max_count: int = DEFAULT_MAX_T_COUNT) -> dict[str, Any]:
    """检查当日 T 次数是否超限。"""
    exceeded = t_count_today >= max_count
    return {
        "exceeded": exceeded,
        "count": t_count_today,
        "max": max_count,
        "reason": f"今日已做 {t_count_today} 次 T，{'已达' if exceeded else '未达'}上限 {max_count}",
    }
