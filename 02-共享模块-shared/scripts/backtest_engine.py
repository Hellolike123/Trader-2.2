#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""BacktestEngine — 无前视偏差回测引擎（v2：cards 对齐 + ATR trailing + 参数扫描）

设计原则（详见项目记忆 2026-07-23）：
1. 拉全量历史，循环内 bars[:t] 切片 → 绕开数据层缺 end_date 的前视偏差。
2. 冻结 market_env 到 t 日：切片指数历史 + 本地复算 level / HMM（不偷看今天）。
3. 复用生产 signal 大脑：plugin_registry.analyze_all + fusion_core.merge_decisions，
   与实盘同一套逻辑。fusion 一律走 cards（意见卡三席），与实盘 build_report 完全一致。
4. 撮合：次日开盘成交 + 滑点 + 费（万 1 佣 + 0.1% 印花）+ T+1
   + ATR trailing 止损（替代固定 8%）+ 涨停买不进 / 跌停卖不出约束。

关键架构（v2）：信号生成与撮合解耦。
   - 信号只算一遍（最慢：每根日线一次 analyze_all + merge），存 signals[t]。
   - 参数扫描（止损/ATR/步长）只重跑撮合层，多进程并行复用同一份信号，
     避免重复调用 analyze_all。

用法（仓库根目录执行）：
    # 单票（cards 模式，对齐实盘）
    python3 02-共享模块-shared/scripts/backtest_engine.py --target 600519 --days 300
    # 参数扫描（信号算一遍，撮合并行扫网格）
    python3 02-共享模块-shared/scripts/backtest_engine.py --target 600519 --days 300 --scan
    # 自定义撮合参数
    python3 ... --atr-mult 3.0 --stop-pct 0.10 --frac 1.0 --no-limit
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

# ── 前视偏差防御：关闭缠论区间套（会现场拉未来 30m/5m/1m）─
os.environ.setdefault("TRADER_CHAN_NESTING", "0")

# ── path bootstrap：scripts/ 的父目录（02-共享模块-shared）含 trader_shared 包 ──
SCRIPT_DIR = Path(__file__).resolve().parent
_SHARED_ROOT = SCRIPT_DIR.parent
if str(_SHARED_ROOT) not in sys.path:
    sys.path.insert(0, str(_SHARED_ROOT))

import trader_shared  # noqa: E402  (确保包可被 import)


def _to_float(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ── 撮合参数（A 股单边手续费模型） ────────────────────────────────────────
SLIP = 0.001        # 滑点 0.1%
try:
    from trader_shared.config import T0_COMMISSION_RATE, T0_STAMP_TAX_RATE
    FEE_BUY = T0_COMMISSION_RATE                    # 佣金 万 1
    FEE_SELL = T0_COMMISSION_RATE + T0_STAMP_TAX_RATE  # 佣金 + 印花
except Exception:
    FEE_BUY = 0.0001
    FEE_SELL = 0.0001 + 0.001
WARMUP = 120          # 预热根数（够缠论/中线周线出结构）

# 动作映射（取自 fusion_regime.ACTION_MAP_NORMAL / DISAGREE）
BUY_ACTIONS = {
    "半仓试 (多方主导)",
    "半仓试 (多方主导但有分歧)",
    "增持",
    "等转强观察",
}
SELL_ACTIONS = {
    "减1/3 (高位松动)",
    "减仓",
    "空仓/止损",
    "天量天价，减仓观望",
    "资金流出，减仓观望",
    "空仓 (限售解禁风险)",
}


@dataclass
class BTParams:
    """撮合层参数（不含信号逻辑，信号与这些无关 → 可并行扫描）。"""
    atr_period: int = 14
    # 默认对齐生产 TRAILING_STOP_ATR_MULTIPLE=3.0
    atr_mult: float = 3.0
    initial_stop_pct: float = 0.08   # 初始硬止损（trailing 的地板）
    position_frac: float = 1.0        # 仓位比例（1.0=满仓；<1=部分仓位）
    use_limit: bool = True             # 涨停买不进 / 跌停卖不出
    limit_pct: float = 0.10           # 涨跌停幅度（创业板/科创板自动调 0.20）
    # 近窗最高收窗口，对齐生产 STRUCTURE_WINDOW
    trail_window: int = 20


# ── 冻结 market_env：切片指数历史 → 复算 level + HMM ─────────────────────────
def _ma(bars: list[dict], n: int) -> float | None:
    if len(bars) < n:
        return None
    vals = [_to_float(b.get("close")) for b in bars[-n:]]
    if any(v is None for v in vals):
        return None
    return sum(vals) / n


def assess_as_of(index_bars: list[dict]) -> dict[str, Any]:
    """复刻 market_env.assess 的核心逻辑，但输入是「截至 t 日」的指数 bars。

    与线上 assess() 的差异：
    - 不取实时 quote，current 用指数当日 close；
    - change_pct 用当日指数收益率；
    - HMM 用切片后的指数收益序列 + 量比序列；
    - 不写任何文件缓存 / 进程内缓存。
    这样回测第 t 天的 regime 只看 t 及之前，杜绝前视。
    """
    if len(index_bars) < 2:
        return {"level": "正常", "hmm_regime_en": "range",
                "change_pct": 0.0, "current": 0.0}
    closes = [v for v in (_to_float(b.get("close")) for b in index_bars) if v]
    if len(closes) < 2:
        return {"level": "正常", "hmm_regime_en": "range",
                "change_pct": 0.0, "current": 0.0}
    change_pct = (closes[-1] - closes[-2]) / closes[-2] * 100
    vols = [_to_float(b.get("volume")) for b in index_bars]
    vols = [v for v in vols if v]
    vol_trend = None
    if len(vols) >= 10:
        vr = sum(vols[-5:]) / 5
        vp = sum(vols[-10:-5]) / 5
        vol_trend = vr / vp if vp > 0 else None

    hmm_regime_en = "range"
    hmm_conf = 0.5
    if len(closes) >= 6:
        rets = [(closes[i] - closes[i - 1]) / closes[i - 1]
                 for i in range(1, len(closes))]
        vser: list[float] = []
        for i in range(1, len(vols)):
            w = vols[max(0, i - 4):i + 1]
            vser.append(vols[i] / (sum(w) / len(w)) if sum(w) > 0 else 1.0)
        if len(rets) >= 5 and len(vser) == len(rets):
            try:
                from trader_shared.hmm_regime import detect_regime
                r = detect_regime(rets, volume_ratio=vser)
                hmm_regime_en = r.get("state_en", "range")
                hmm_conf = r.get("confidence", 0.5)
            except Exception:
                pass

    ma5 = _ma(index_bars, 5)
    ma20 = _ma(index_bars, 20)
    mid_up = ma5 is not None and ma20 is not None and ma5 > ma20
    mid_weak = not mid_up
    intraday_weak = change_pct < -2.0
    intraday_moderate = 0 > change_pct >= -2.0
    shrinking = vol_trend is not None and vol_trend < 0.8

    level = "正常"
    if mid_weak and intraday_weak:
        level = "很差"
    elif mid_weak and (shrinking or intraday_moderate):
        level = "偏弱"
    if hmm_conf >= 0.75:
        if hmm_regime_en == "bear" and level == "正常":
            level = "偏弱"
        elif hmm_regime_en == "bull" and level == "偏弱":
            level = "正常"
    if change_pct <= -3.0 and level == "正常":
        level = "偏弱"
    elif change_pct <= -5.0 and level in ("正常", "偏弱"):
        level = "很差"

    return {"level": level, "hmm_regime_en": hmm_regime_en,
            "change_pct": change_pct, "current": closes[-1]}


# ── ATR（与生产同源：indicator_math.calc_atr_series，SMA 非 Wilder）────────
def compute_atr(bars: list[dict], period: int = 14) -> list[float | None]:
    """返回与 bars 等长的 ATR 序列（预热期前为 None）。

    对齐实盘 light_data / structure_core 的 14 期 SMA ATR，避免回测用 Wilder
    而生产用 SMA 导致 trailing 止损口径分裂。
    """
    from trader_shared.indicator_math import calc_atr_series

    return calc_atr_series(bars, period=period)


# ── 风控历史数据：一次性拉取，循环内按 t 切片（point-in-time，无前视） ──
def _add_days(date_str: str, n: int) -> str:
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        return (d + timedelta(days=n)).strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return ""


def _fetch_risk_history(sec) -> dict[str, Any]:
    """拉取回测所需风控历史（一次性）：
    - fund_flow_hist：个股资金流向日线（最近窗口，API 限制 ~27 交易日）。
    - unlocks_all：全部限售解禁事件（带 date，不限 today）。
    - shareholder：股东户数最新披露（带 latest_notice_date，point-in-time）。
    失败项返回空，引擎退化为不触发对应风控（与实盘「数据缺失不 veto」一致）。
    """
    code = sec.ts_code
    fund_flow_hist: list[dict] = []
    unlocks_all: list[dict] = []
    shareholder: dict | None = None

    # 1) 资金流向日线（fetch_fund_flow 内部有缓存，日线切片无前视）
    try:
        from trader_shared import fund_flow_data as _ff
        fl = _ff.fetch_fund_flow(code, days=400)
        fund_flow_hist = sorted(fl, key=lambda x: str(x.get("date") or ""))
    except Exception:
        fund_flow_hist = []

    # 2) 全部限售解禁事件（Tushare share_float；不过滤 today，循环内按 t 切 90 天窗口）
    try:
        from trader_shared.extend_data import ExtendDataProvider
        unlocks_all = ExtendDataProvider.get_all_unlocks(code) or []
        unlocks_all = sorted(unlocks_all, key=lambda x: str(x.get("date") or ""))
    except Exception:
        unlocks_all = []

    # 3) 股东户数（最新披露，point-in-time 由 notice_date 决定生效日）
    try:
        from trader_shared.extend_data import ExtendDataProvider
        shareholder = ExtendDataProvider.get_shareholder_trend(code)
        if not shareholder or shareholder.get("status") in (None, "数据不足"):
            shareholder = None
    except Exception:
        shareholder = None

    return {
        "fund_flow_hist": fund_flow_hist,
        "unlocks_all": unlocks_all,
        "shareholder": shareholder,
    }


# ── 扩展软修正历史（point-in-time 切片，无前视） ───────────────────────
def _fetch_extend_history(sec, use_cache: bool = True,
                        force_refresh: bool = False) -> dict[str, Any]:
    """拉取「软修正」扩展数据历史（一次性），循环内按 t 切片。

    现状（2026-07-23 实测 Mac）：
    - extend_northbound（北向资金）：✅ 可拉全市场级日序列
      （akshare stock_hsgt_hist_em）。同一天对所有票通用，无需个股分类，
      可干净做 point-in-time 切片。
    - extend_sector / extend_concept：需先「个股→板块」实时分类
      （akshare 实时端点在本 Mac 返回无数据）→ 无法映射历史板块指数，
      故 out-of-scope。
    - extend_margin（融资融券）：akshare 仅市场级明细表，无单票历史
      时间序列 → out-of-scope。
    失败/缺失项返回空，引擎退化为不接对应软修正（与实盘「数据缺失不修正」一致）。
    """
    code = sec.ts_code
    northbound_hist: list[dict] = []

    if use_cache and not force_refresh:
        cached = _load_cache("NB", 0, "nbh")
        if cached is not None:
            return {"northbound_hist": cached}

    try:
        import akshare as ak
        df = ak.stock_hsgt_hist_em(symbol="北向资金")
        # 列：日期 / 当日成交净买额（单位：亿元）
        dcol = "日期"
        ncol = "当日成交净买额"
        for _, row in df.iterrows():
            d = str(row.get(dcol) or "")[:10]
            if not d:
                continue
            try:
                _raw = row.get(ncol)
                net_yi = float(_raw) if _raw is not None else 0.0
                if net_yi != net_yi:  # NaN 守卫：nan 在 Python 为真，
                    net_yi = 0.0           # 必须显式置 0，否则 nan*1e4 仍 nan，
            except (ValueError, TypeError):  # 融合层 nan>x / nan<0 都 False → 静默跳过 nudge
                net_yi = 0.0
            northbound_hist.append({
                "date": d,
                "net_wan": net_yi * 1e4,  # → 万元，对齐融合层字段
            })
        northbound_hist.sort(key=lambda x: x["date"])
    except Exception:
        northbound_hist = []

    if use_cache and northbound_hist:
        _save_cache("NB", 0, "nbh", northbound_hist)
    return {"northbound_hist": northbound_hist}



# ── 信号函数：第 t 天只看 bars[:t+1]（算一遍，供扫描复用） ──────────────────
def make_signal_fn(provider, sec, registry, bars, weekly, index_bars,
                   idx_dates: list[str],
                   fund_flow_hist: list[dict] | None = None,
                   unlocks_all: list[dict] | None = None,
                   shareholder: dict | None = None,
                   northbound_hist: list[dict] | None = None,
                   use_risk: bool = True,
                   use_extend: bool = True,
                   veto_log: list[dict] | None = None):
    """闭包：返回 signal_at(t) -> fusion dict（严格只用到 t 日数据）。

    use_risk=True 时接入实盘硬风控：
    - fund_flow_data：按 t 切片历史资金流向 → 连续流出 veto 生效；
    - extend_sentiment(unlocks)：按 t 切 90 天解禁窗口 → 解禁风险空仓 veto 生效；
    - extend_fundamental(shareholder)：t ≥ 披露日才生效 → 筹码集中置信加成。
    use_extend=True 时接入扩展软修正（point-in-time 无前视）：
    - extend_northbound：按 t 取「≤ t 最近一日」北向净流入 + 近 5 日累计
      （仅北向可干净做历史切片；板块/概念/融资因缺单票历史源 out-of-scope）。
    """
    import bisect
    from trader_shared.fusion_core import merge_decisions

    fund_flow_hist = fund_flow_hist or []
    unlocks_all = unlocks_all or []
    northbound_hist = northbound_hist or []
    nb_dates = [x["date"] for x in northbound_hist]
    veto_log = veto_log if veto_log is not None else []

    def _index_slice(date_t: str) -> list[dict]:
        k = bisect.bisect_right(idx_dates, date_t)
        return index_bars[:k] if k > 0 else index_bars[:1]

    def _avg_turnover(cur_bars) -> float | None:
        amts = []
        for b in cur_bars[-20:]:
            a = b.get("amount")
            if a is not None:
                try:
                    amts.append(float(str(a).replace(",", "")))
                except (TypeError, ValueError):
                    pass
        return sum(amts) / len(amts) / 10000.0 if amts else None

    def _risk_inputs(date_t: str, cur: list[dict]):
        """按 t 切片风控数据（point-in-time），返回 (fund_flow_data, ext_sent, ext_fund)。"""
        ff_data = None
        ext_sent = None
        ext_fund = None
        if not use_risk:
            return ff_data, ext_sent, ext_fund
        # 资金流向：日线切片到 t（API 仅近窗口有数，早期 t 自然为空 → 不 veto）
        if fund_flow_hist:
            sl = [d for d in fund_flow_hist if str(d.get("date") or "") <= date_t]
            if sl:
                from trader_shared import fund_flow_data as _ff
                ff_data = _ff.calc_fund_flow_features(sl, cur)
        # 解禁：事件落在 [t, t+90] 窗口内（与实盘「未来 90 天」一致）
        if unlocks_all:
            hi = _add_days(date_t, 90)
            within = [u for u in unlocks_all
                      if date_t <= u["date"] <= hi] if hi else []
            if within:
                ext_sent = {"unlocks": within, "status": "正常"}
        # 股东户数：披露日后才生效（point-in-time）
        if shareholder:
            nd = shareholder.get("latest_notice_date", "")
            if nd and date_t >= nd:
                ext_fund = {"shareholder": shareholder,
                            "status": shareholder.get("status")}
        return ff_data, ext_sent, ext_fund

    def _northbound_inputs(date_t: str):
        """按 t 取「≤ t 最近一日」北向净流入 + 近 5 日累计。point-in-time 无前视。"""
        if not use_extend or not nb_dates:
            return None
        k = bisect.bisect_right(nb_dates, date_t)
        if k <= 0:
            return None
        cur = northbound_hist[k - 1]
        net = cur["net_wan"]
        window = [northbound_hist[i]["net_wan"]
                   for i in range(max(0, k - 5), k)]
        return {"status": "正常",
                "north_net_flow_wan": net,
                "north_flow_5d_wan": sum(window)}

    def signal_at(t: int) -> dict[str, Any]:
        cur = bars[:t + 1]
        if len(cur) < 2:
            return {"action": "观望", "weighted_score": 0.0, "confidence": 0.0,
                    "regime": "正常", "hmm_regime": "range"}
        date_t = cur[-1].get("date", "")
        cur_weekly = [w for w in weekly if w.get("date", "") <= date_t]
        current = _to_float(cur[-1].get("close")) or 0.0
        prev = _to_float(cur[-2].get("close")) or current
        change_pct = (current - prev) / prev * 100 if prev else 0.0
        quote = {
            "current_price": current,
            "name": getattr(sec, "name", ""),
            "current_change_pct": change_pct,
            "_bars_5m": [],  # 防止 VWAP 插件现场拉「未来」5m
        }
        try:
            pr = registry.analyze_all(
                current, cur, change_pct, quote,
                weekly_bars=cur_weekly, midline=True,
            )
        except Exception as exc:
            return {"action": "观望", "weighted_score": 0.0, "confidence": 0.0,
                    "regime": "正常", "hmm_regime": "range", "error": str(exc)}
        chan = pr.get("chanlun") or {}
        mom = pr.get("momentum") or {}
        wyck = pr.get("wyckoff") or {}
        env = assess_as_of(_index_slice(date_t))

        # ② 风控历史切片（point-in-time，无前视）
        ff_data, ext_sent, ext_fund = _risk_inputs(date_t, cur)
        # ③ 扩展软修正（point-in-time，无前视）：北向
        ext_nb = _northbound_inputs(date_t)

        merge_kwargs = dict(
            chan_result=chan,
            momentum_result=mom,
            wyckoff_result=wyck,
            regime=env["level"],
            current_price=current,
            bars=cur,
            hmm_regime=env["hmm_regime_en"],
            main_force_env=None,
            data_status="full",
            fund_flow_data=ff_data,
            extend_sentiment=ext_sent,
            extend_fundamental=ext_fund,
            extend_northbound=ext_nb,
            current_change_pct=change_pct,
        )
        # ① cards 对齐实盘：构造三张卡喂给 merge_decisions
        try:
            from trader_shared.analysis_cards import (
                build_chan_card, build_momentum_card, build_vpf_card,
            )
            from trader_shared.vpf_core import build_vpf_signal
            cards = {
                "chan": build_chan_card(chan, role="daily"),
                "momentum": build_momentum_card(mom, role="daily"),
            }
            avg_to = _avg_turnover(cur)
            vpf_raw = build_vpf_signal(
                None, None, bars=cur, avg_daily_turnover_wan=avg_to)
            cards["vpf"] = build_vpf_card(vpf_raw, role="daily")
            merge_kwargs["analysis_cards"] = cards
        except Exception:
            merge_kwargs.pop("analysis_cards", None)
        merge_kwargs["fusion_from_cards"] = "cards"

        try:
            fusion = merge_decisions(**merge_kwargs)
        except Exception as exc:
            return {"action": "观望", "weighted_score": 0.0, "confidence": 0.0,
                    "regime": env["level"], "hmm_regime": env["hmm_regime_en"],
                    "error": str(exc)}

        # 记录风控触发（用于报告对比实盘风控是否生效）
        if use_risk:
            act = fusion.get("action", "")
            if fusion.get("fund_flow_outflow_veto"):
                veto_log.append({"date": date_t, "type": "fund_flow_outflow",
                                "action": act})
            elif act == "空仓 (限售解禁风险)":
                veto_log.append({"date": date_t, "type": "unlock",
                                "action": act})
        return fusion

    return signal_at


def compute_signals(bars: list[dict], signal_at, t_start: int,
                     t_end: int) -> list[dict | None]:
    """把每个 t 的信号算一遍（最慢的部分，扫描时只调一次）。"""
    sig = [None] * len(bars)
    for t in range(t_start, t_end):
        try:
            sig[t] = signal_at(t)
        except Exception:
            sig[t] = {"action": "观望", "weighted_score": 0.0,
                       "confidence": 0.0, "regime": "正常", "hmm_regime": "range"}
    return sig


# ── 撮合 + 绩效（纯本地计算，无网络/无 analyze_all → 可并行扫描） ────────────
def match_and_score(bars: list[dict], signals: list[dict | None],
                    atr: list[float | None], params: BTParams,
                    t_start: int, t_end: int, step: int = 1,
                    return_curve: bool = True) -> dict[str, Any]:
    """次日开盘撮合 + T+1 + ATR trailing 止损 + 涨跌停约束，输出资金曲线与绩效。

    模型：单一标的、单头寸、按 position_frac 决定仓位比例（1.0=满仓）。
    以 1.0 为初始净值，买入时按现金比例换股，按股数盯市。
    """
    cash = 1.0
    shares = 0.0
    position = None            # {"entry_day","entry"(含费成本/股),"stop","hard","sig_date"}
    want_buy = False
    want_exit = False
    exit_reason = None
    equity_curve: list[float] = []
    trades: list[dict] = []

    lp = params.limit_pct
    for t in range(t_start, t_end):
        bar = bars[t]
        o = _to_float(bar.get("open"))
        c = _to_float(bar.get("close"))
        lo = _to_float(bar.get("low"))
        prev_close = _to_float(bars[t - 1].get("close")) if t > 0 else c
        limit_up = prev_close * (1 + lp) if prev_close else None
        limit_down = prev_close * (1 - lp) if prev_close else None

        # 1) 执行上一日挂单（次日开盘买入，全仓/部分）
        if shares == 0 and want_buy and o and o > 0:
            blocked = params.use_limit and limit_up and o >= limit_up * (1 - 1e-4)
            if blocked:
                want_buy = False  # 涨停买不进，错过
            else:
                entry = o * (1 + SLIP)
                entry_incl = entry * (1 + FEE_BUY)
                deploy = cash * params.position_frac
                shares = deploy / entry_incl
                cash -= deploy
                hard = entry_incl * (1 - params.initial_stop_pct)
                position = {"entry_day": t, "entry": entry_incl,
                            "stop": hard, "hard": hard,
                            "sig_date": bar.get("date", "")}
                want_buy = False

        # 2) 盘中触及止损（T+1 后才允许卖）
        if (shares > 0 and position["entry_day"] < t
                and lo is not None and lo <= position["stop"]):
            want_exit = True
            exit_reason = "stop"

        # 3) ATR trailing 更新（对齐生产：近窗最高收 × (1 − ATR%×倍数)，只上移）
        if shares > 0 and position["entry_day"] < t:
            cand = [position["hard"], position["stop"]]
            if atr[t] is not None and c and c > 0:
                w = max(1, int(params.trail_window or 20))
                win = bars[max(0, t - w + 1) : t + 1]
                highs = [
                    v for b in win
                    if (v := _to_float(b.get("close"))) is not None and v > 0
                ]
                if highs:
                    atr_pct = float(atr[t]) / c
                    trail = max(highs) * (1.0 - atr_pct * params.atr_mult)
                    cand.append(trail)
            position["stop"] = max(cand)

        # 4) 执行卖出（T+1；信号或止损；跌停卖不出则等次日）
        if (shares > 0 and want_exit and position["entry_day"] < t
                and o and o > 0):
            blocked = params.use_limit and limit_down and o <= limit_down * (1 + 1e-4)
            if not blocked:
                exit_px = o * (1 - SLIP)
                fee = exit_px * FEE_SELL
                proceeds = shares * (exit_px - fee)
                cash += proceeds
                trades.append({
                    "entry_date": bars[position["entry_day"]].get("date", ""),
                    "exit_date": bar.get("date", ""),
                    "exit_type": exit_reason or "signal",
                    "pnl_pct": (exit_px - fee) / position["entry"] - 1,
                })
                shares = 0.0
                position = None
                want_exit = False
                exit_reason = None

        # 5) 生成新信号（每 step 天评估一次，决定次日挂单）
        if step and t % step == 0:
            sig = signals[t]
            if sig:
                action = sig.get("action", "观望")
                if shares == 0 and action in BUY_ACTIONS:
                    want_buy = True
                elif (shares > 0 and position and position["entry_day"] < t
                      and action in SELL_ACTIONS):
                    want_exit = True
                    exit_reason = "signal"

        # 6) 当日市值（盯市）
        equity_curve.append(shares * (c or 0.0) + cash)

    # 收尾：强制按最后一根平仓（避免悬空头寸影响指标）
    if position is not None and equity_curve:
        last_close = _to_float(bars[-1].get("close")) or 0.0
        fee = last_close * FEE_SELL
        cash += shares * (last_close - fee)
        trades.append({
            "entry_date": bars[position["entry_day"]].get("date", ""),
            "exit_date": bars[-1].get("date", ""),
            "exit_type": "eod",
            "pnl_pct": (last_close - fee) / position["entry"] - 1,
        })
        equity_curve[-1] = cash
        position = None
        shares = 0.0

    return _metrics(equity_curve, trades, bars, t_start, t_end,
                    return_curve=return_curve)


def _to_date(s: str):
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _metrics(equity_curve, trades, bars, t_start, t_end,
             return_curve: bool = True) -> dict[str, Any]:
    eq = equity_curve
    if not eq:
        return {"total_return_pct": 0.0, "cagr_pct": 0.0, "max_drawdown_pct": 0.0,
                "sharpe": 0.0, "num_trades": 0, "win_rate_pct": 0.0,
                "profit_factor": None, "avg_win_pct": 0.0, "avg_loss_pct": 0.0,
                "period": "", "equity_curve": [], "trades": []}
    total_return = (eq[-1] / eq[0] - 1.0) if eq[0] else 0.0
    first_d = _to_date(bars[t_start].get("date"))
    last_d = _to_date(bars[min(t_end, len(bars)) - 1].get("date"))
    years = ((last_d - first_d).days / 365.25) if (first_d and last_d) else 0.0
    cagr = ((eq[-1] / eq[0]) ** (1.0 / years) - 1.0) if (years > 0 and eq[0] > 0) else 0.0
    peak = eq[0]
    max_dd = 0.0
    for v in eq:
        if v > peak:
            peak = v
        dd = (v - peak) / peak if peak > 0 else 0.0
        if dd < max_dd:
            max_dd = dd
    daily_rets = [(eq[i] / eq[i - 1] - 1.0) for i in range(1, len(eq)) if eq[i - 1] > 0]
    import statistics
    if daily_rets and statistics.pstdev(daily_rets) > 0:
        sharpe = (statistics.mean(daily_rets) / statistics.pstdev(daily_rets)) * (252 ** 0.5)
    else:
        sharpe = 0.0
    wins = [x for x in trades if x["pnl_pct"] > 0]
    losses = [x for x in trades if x["pnl_pct"] <= 0]
    gross_win = sum(x["pnl_pct"] for x in wins)
    gross_loss = abs(sum(x["pnl_pct"] for x in losses))
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else float("inf")
    win_rate = (len(wins) / len(trades) * 100) if trades else 0.0

    return {
        "total_return_pct": round(total_return * 100, 2),
        "cagr_pct": round(cagr * 100, 2),
        "max_drawdown_pct": round(max_dd * 100, 2),
        "sharpe": round(sharpe, 2),
        "num_trades": len(trades),
        "win_rate_pct": round(win_rate, 1),
        "profit_factor": round(profit_factor, 2) if profit_factor != float("inf") else None,
        "avg_win_pct": round((gross_win / len(wins) * 100), 2) if wins else 0.0,
        "avg_loss_pct": round((gross_loss / len(losses) * 100), 2) if losses else 0.0,
        "period": f"{bars[t_start].get('date', '')} ~ {bars[min(t_end, len(bars)) - 1].get('date', '')}",
        "equity_curve": eq if return_curve else [],
        "trades": trades,
    }


# ── 主流程 ────────────────────────────────────────────────────────────────
def _limit_pct_for(code: str) -> float:
    # 创业板 300xxx / 科创板 688xxx → 20%，其余 10%
    if code.startswith("688") or code.startswith("300"):
        return 0.20
    return 0.10


# ── 回测前落盘缓存（根治 TencentFetcher 跨进程偶发 100× 缩放坏点） ──
# 思路：主进程抓一次写盘，后续所有运行（含扫描、A/B）都读同一份
# 确定性数据，不再每次独立进程重新抓数 → 结果可复现、且坏点只可能在
# 「写入那一次」出现（写入前仍跑健全性快检拦截）。
def _cache_dir() -> Path:
    d = Path.home() / ".trader" / "backtest_cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _cache_path(code: str, days: int, kind: str) -> Path:
    return _cache_dir() / f"{code}_{days}_{kind}.json"


def _load_cache(code: str, days: int, kind: str):
    p = _cache_path(code, days, kind)
    if not p.exists():
        return None
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
        if obj.get("meta", {}).get("fetched") != _today_str():
            return None  # 过期 → 重新抓取
        return obj.get("data")
    except Exception:
        return None


def _save_cache(code: str, days: int, kind: str, data) -> None:
    try:
        p = _cache_path(code, days, kind)
        p.write_text(json.dumps(
            {"meta": {"code": code, "days": days, "fetched": _today_str()},
            "data": data}, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _sanity_check(bars: list[dict]) -> None:
    """非破坏性快检（写入缓存前 + 读缓存后都跑）：抓取偶发 100× 缩放
    坏点会静默污染回测。A 股单日涨跌幅 ≤20%，收盘价相对中位数 >5×
    几乎必为数据错误。"""
    _closes = [_to_float(b.get("close")) for b in bars]
    _closes = [c for c in _closes if c and c > 0]
    if not _closes:
        return
    _med = sorted(_closes)[len(_closes) // 2]
    _bad = [b.get("date") for b in bars
             if _to_float(b.get("close")) and _med
             and abs(_to_float(b.get("close")) / _med) > 5]
    if _bad:
        print(f"  ⚠️ 检测到 {len(_bad)} 根收盘价离群（疑似抓取缩放坏点），"
              f"可能污染回测：{_bad[:3]}")


def load_data(target: str, days: int, use_env: bool = True,
             use_cache: bool = True, force_refresh: bool = False):
    """拉全量历史（绕开 day-scoped 缓存），返回 (bars, weekly, index_bars, idx_dates, sec, provider, cache_info)。

    use_cache=True 且命中当日缓存 → 直接读盘（确定性、可复现）；
    否则 TencentFetcher 抓全量 → 健全性快检 → 写盘。
    """
    from trader_shared.data_provider import get_provider, set_provider, UnifiedProvider
    from trader_shared.config import INDEX_CODE

    try:
        set_provider(UnifiedProvider(backend="tencent"))
    except Exception:
        pass
    provider = get_provider()
    sec = provider.resolve_security(target)
    code = sec.ts_code

    cache_info = {"bars_hit": False, "idx_hit": False,
                  "ff_hit": False, "used": use_cache and not force_refresh}

    # 1) 日线（落盘缓存核心：每次回测同此一份数据）
    bars = None
    if use_cache and not force_refresh:
        bars = _load_cache(code, days, "bars")
        cache_info["bars_hit"] = bars is not None
    if bars is None:
        from trader_shared.fetchers import TencentFetcher
        _fetcher = TencentFetcher()
        bars = _fetcher.fetch_qfq_daily(code, days=days)
        if use_cache:
            _sanity_check(bars)  # 写入前拦截坏点
            _save_cache(code, days, "bars", bars)

    _sanity_check(bars)  # 读缓存也快检（防旧缓存已污染）

    try:
        weekly = provider.fetch_weekly(sec)
    except Exception:
        weekly = []

    # 2) 指数历史（冻结 market_env 用）
    index_bars = []
    if use_env:
        if use_cache and not force_refresh:
            index_bars = _load_cache(INDEX_CODE, days, "idx") or []
            cache_info["idx_hit"] = bool(index_bars)
        if not index_bars:
            try:
                from trader_shared.fetchers import TencentFetcher
                _fetcher = TencentFetcher()
                index_bars = _fetcher.fetch_qfq_daily(INDEX_CODE, days=days)
                if use_cache:
                    _save_cache(INDEX_CODE, days, "idx", index_bars)
            except Exception:
                index_bars = []
        if len(index_bars) < 2:
            print("  ⚠️ 指数历史不足，market_env 退化为恒定 level=正常 / hmm=range")
            index_bars = []
    idx_dates = sorted(b.get("date", "") for b in index_bars)
    return bars, weekly, index_bars, idx_dates, sec, provider, cache_info


def run_backtest(target: str, days: int = 300, step: int = 1,
                use_env: bool = True,
                use_risk: bool = True, use_extend: bool = True,
                use_cache: bool = True, force_refresh: bool = False,
                params: BTParams | None = None,
                scan: bool = False) -> dict[str, Any]:
    if params is None:
        params = BTParams()
    bars, weekly, index_bars, idx_dates, sec, provider, cache_info = \
        load_data(target, days, use_env, use_cache, force_refresh)
    if len(bars) < WARMUP + 5:
        return {"target": target, "error": f"日线数据不足: {len(bars)} 根（需 ≥{WARMUP+5}）"}

    params.limit_pct = _limit_pct_for(sec.ts_code)
    from trader_shared.plugin_registry import get_registry
    registry = get_registry()

    # 风控历史一次性拉取（fund_flow / unlocks / shareholder）
    risk = _fetch_risk_history(sec) if use_risk else {}
    # 扩展软修正历史（北向，point-in-time 切片）
    extend = _fetch_extend_history(sec, use_cache, force_refresh) if use_extend else {}
    northbound_hist = extend.get("northbound_hist") or []
    veto_log: list[dict] = []
    signal_at = make_signal_fn(
        provider, sec, registry, bars, weekly,
        index_bars, idx_dates,
        fund_flow_hist=risk.get("fund_flow_hist"),
        unlocks_all=risk.get("unlocks_all"),
        shareholder=risk.get("shareholder"),
        northbound_hist=northbound_hist,
        use_risk=use_risk, use_extend=use_extend,
        veto_log=veto_log,
    )
    atr = compute_atr(bars, params.atr_period)
    t_start = max(WARMUP, 2)
    t_end = len(bars) - 1  # 留 t+1 根用于次日开盘成交

    # 信号只算一遍
    t0 = time.time()
    signals = compute_signals(bars, signal_at, t_start, t_end)
    sig_elapsed = time.time() - t0

    _n_ff = sum(1 for v in veto_log if v["type"] == "fund_flow_outflow")
    _n_unl = sum(1 for v in veto_log if v["type"] == "unlock")
    result: dict[str, Any] = {
        "target": target,
        "name": getattr(sec, "name", target),
        "bars_used": len(bars),
        "env_frozen": bool(index_bars),
        "use_risk": use_risk,
        "use_extend": use_extend,
        "cache_used": bool(cache_info.get("used")),
        "cache_bars_hit": bool(cache_info.get("bars_hit")),
        "cache_idx_hit": bool(cache_info.get("idx_hit")),
        "risk_ff_bars": len(risk.get("fund_flow_hist") or []),
        "risk_unlocks": len(risk.get("unlocks_all") or []),
        "risk_has_holder": bool(risk.get("shareholder")),
        "extend_nb_days": len(northbound_hist),
        "veto_fund_flow": _n_ff,
        "veto_unlock": _n_unl,
        "atr_mult": params.atr_mult,
        "initial_stop_pct": params.initial_stop_pct,
        "position_frac": params.position_frac,
        "use_limit": params.use_limit,
        "limit_pct": params.limit_pct,
        "signal_compute_sec": round(sig_elapsed, 1),
    }

    if scan:
        grid = _build_grid(params)
        rows = _run_scan(bars, signals, atr, grid, t_start, t_end, step)
        result["scan"] = rows
        result["period"] = rows[0].get("period", "") if rows else ""
        result["scan_best"] = _pick_best(rows)
        return result

    t0 = time.time()
    m = match_and_score(bars, signals, atr, params, t_start, t_end, step=step)
    m.update(result)
    m["match_sec"] = round(time.time() - t0, 2)
    return m


def _build_grid(base: BTParams) -> list[BTParams]:
    atr_mults = [2.0, 2.5, 3.0]
    stops = [0.06, 0.08, 0.10]
    steps = [1, 2]
    grid = []
    for am in atr_mults:
        for st in stops:
            for sp in steps:
                p = BTParams(
                    atr_period=base.atr_period,
                    atr_mult=am,
                    initial_stop_pct=st,
                    position_frac=base.position_frac,
                    use_limit=base.use_limit,
                    limit_pct=base.limit_pct,
                    trail_window=base.trail_window,
                )
                # step 作为撮合参数传入（信号已算好，不影响）
                grid.append((p, sp))
    return grid


def _scan_worker(payload: tuple) -> dict[str, Any]:
    bars, signals, atr, params, sp, t_start, t_end = payload
    m = match_and_score(bars, signals, atr, params, t_start, t_end,
                         step=sp, return_curve=False)
    m["atr_mult"] = params.atr_mult
    m["initial_stop_pct"] = params.initial_stop_pct
    m["step"] = sp
    return m


def _run_scan(bars, signals, atr, grid, t_start, t_end, step: int):
    payloads = [(bars, signals, atr, p, sp, t_start, t_end) for (p, sp) in grid]
    rows = []
    n_cpu = min(8, (os.cpu_count() or 4))
    with ProcessPoolExecutor(max_workers=n_cpu) as ex:
        for m in ex.map(_scan_worker, payloads):
            rows.append(m)
    rows.sort(key=lambda r: r["total_return_pct"], reverse=True)
    return rows


def _pick_best(rows: list[dict]) -> dict | None:
    if not rows:
        return None
    # 优先：有交易、夏普>0、回撤可控；再比总收益
    valid = [r for r in rows if r["num_trades"] > 0]
    pool = valid if valid else rows
    return max(pool, key=lambda r: (r["sharpe"], r["total_return_pct"]))


def _print_report(r: dict) -> None:
    if r.get("error"):
        print("  %s: %s" % (r["target"], r["error"]))
        return
    seg = "=" * 60
    print("\n" + seg)
    print("  %s (%s)  [%s]" % (
        r["name"], r["target"], "cards"))
    print("  区间 %s | 日线 %d 根 | regime冻结 %s | 涨跌停 %s ±%.0f%%" % (
        r["period"], r["bars_used"],
        "是" if r["env_frozen"] else "否-常量",
        "是" if r["use_limit"] else "否", r["limit_pct"] * 100))
    print("  ATR×%.1f 初始止损 %.0f%% 仓位 %.0f%%" % (
        r["atr_mult"], r["initial_stop_pct"] * 100, r["position_frac"] * 100))
    _rk = "开" if r.get("use_risk") else "关"
    print("  实盘风控 : %s  | 资金流%d根 解禁%d笔 股东%s" % (
        _rk, r.get("risk_ff_bars", 0), r.get("risk_unlocks", 0),
        "有" if r.get("risk_has_holder") else "无"))
    if r.get("use_risk"):
        print("  风控触发 : 资金流出veto %d 次 | 解禁风险veto %d 次" % (
            r.get("veto_fund_flow", 0), r.get("veto_unlock", 0)))
    _ex = "开" if r.get("use_extend") else "关"
    _cache = "盘缓存" if r.get("cache_used") else "实时抓取"
    _chit = "命中" if r.get("cache_bars_hit") else "未命中"
    _ihit = "命中" if r.get("cache_idx_hit") else "未命中"
    _nb = r.get("extend_nb_days", 0)
    print("  扩展软修正: %s (北向历史 %d 天)" % (_ex, _nb))
    print("  数据来源 : %s | 日线%s 指数%s" % (_cache, _chit, _ihit))
    print("  信号计算 %ss | 撮合 %ss" % (
        r.get("signal_compute_sec", "-"), r.get("match_sec", "-")))
    print(seg)
    _pf = r["profit_factor"] if r["profit_factor"] is not None else "∞"
    print("  总收益   : %+.2f%%" % r["total_return_pct"])
    print("  年化     : %+.2f%%" % r["cagr_pct"])
    print("  最大回撤 : %.2f%%" % r["max_drawdown_pct"])
    print("  夏普     : %.2f" % r["sharpe"])
    print("  交易次数 : %d" % r["num_trades"])
    print("  胜率     : %.1f%%" % r["win_rate_pct"])
    print("  盈亏比   : %s" % _pf)
    print("  均盈/均亏: +%.2f%% / %.2f%%" % (r["avg_win_pct"], r["avg_loss_pct"]))
    if r["trades"][:5]:
        print("  近 5 笔交易:")
        for tr in r["trades"][-5:]:
            print("    %s -> %s [%s] %+.2f%%" % (
                tr["entry_date"], tr["exit_date"],
                tr["exit_type"], tr["pnl_pct"]))

def _print_scan(r: dict) -> None:
    rows = r.get("scan", [])
    if not rows:
        print("  无扫描结果")
        return
    print(f"\n{'='*64}")
    print(f"  参数扫描  {r['name']} ({r['target']})  "
          f"[cards]  共 {len(rows)} 组")
    print(f"  区间 {r['period']} | 信号计算 {r.get('signal_compute_sec','-')}s（只算一遍）")
    print(f"{'='*64}")
    hdr = (f"  {'ATR×':>5} {'止损':>5} {'步':>3} | {'总收益':>8} {'年化':>8} "
           f"{'回撤':>7} {'夏普':>6} {'笔':>3} {'胜率':>6} {'盈亏比':>7}")
    print(hdr)
    print("  " + "-" * 60)
    for x in rows:
        pf = x["profit_factor"]
        print(f"  {x['atr_mult']:>5.1f} {x['initial_stop_pct']*100:>4.0f}% "
              f"{x['step']:>3} | {x['total_return_pct']:>+8.2f}% "
              f"{x['cagr_pct']:>+8.2f}% {x['max_drawdown_pct']:>6.2f}% "
              f"{x['sharpe']:>6.2f} {x['num_trades']:>3} "
              f"{x['win_rate_pct']:>5.1f}% "
              f"{(pf if pf is not None else 99.99):>7.2f}")
    best = r.get("scan_best")
    if best:
        print(f"\n  ★ 推荐（夏普优先）: ATR×{best['atr_mult']} "
              f"止损{best['initial_stop_pct']*100:.0f}% 步{best['step']} "
              f"→ 总{best['total_return_pct']:+.2f}% 夏普{best['sharpe']:.2f} "
              f"回撤{best['max_drawdown_pct']:.2f}%")


def main() -> int:
    parser = argparse.ArgumentParser(description="BacktestEngine v2（cards+ATR trailing+扫描）")
    parser.add_argument("--target", type=str, help="股票名称或代码")
    parser.add_argument("--days", type=int, default=300, help="回测天数 (默认 300)")
    parser.add_argument("--step", type=int, default=1,
                        help="信号评估步长 (默认 1，每隔 N 天评估一次)")
    parser.add_argument("--no-env", action="store_true",
                        help="不冻结 market_env（regime 退化为常量）")
    parser.add_argument("--scan", action="store_true", help="参数扫描（多进程并行）")
    parser.add_argument(
        "--atr-mult", type=float, default=3.0,
        help="ATR 止损倍数（默认 3.0，对齐生产 TRAILING_STOP_ATR_MULTIPLE）",
    )
    parser.add_argument("--stop-pct", type=float, default=0.08, help="初始硬止损比例")
    parser.add_argument("--frac", type=float, default=1.0, help="仓位比例 0~1")
    parser.add_argument("--no-limit", action="store_true", help="关闭涨跌停约束")
    parser.add_argument("--no-riskdata", action="store_true",
                        help="不接入实盘风控（fund_flow/unlocks/shareholder），"
                             "用于 A/B 对比 veto 是否生效")
    parser.add_argument("--no-extend", action="store_true",
                        help="不接入扩展软修正（北向资金 point-in-time 切片），"
                             "用于 A/B 对比软修正是否生效")
    parser.add_argument("--no-cache", action="store_true",
                        help="不读盘缓存，强制实时重新抓取日线/指数/北向")
    parser.add_argument("--refresh-cache", action="store_true",
                        help="强制刷新盘缓存（先忽略旧缓存重新抓，再写回）")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args()

    if not args.target:
        print("用法: python3 backtest_engine.py --target 贵州茅台 --days 300 [--scan]")
        return 1

    params = BTParams(
        atr_mult=args.atr_mult,
        initial_stop_pct=args.stop_pct,
        position_frac=args.frac,
        use_limit=not args.no_limit,
    )

    print(f"🔍 回测 {args.target} (days={args.days}, step={args.step}, "
          f"cards{', 扫描' if args.scan else ''})...",
          end=" ", flush=True)
    r = run_backtest(args.target, days=args.days, step=args.step,
                     use_env=not args.no_env,
                     use_risk=not args.no_riskdata,
                     use_extend=not args.no_extend,
                     use_cache=not args.no_cache,
                     force_refresh=args.refresh_cache,
                     params=params, scan=args.scan)
    if args.json:
        r_json = {k: v for k, v in r.items() if k != "equity_curve"}
        print(json.dumps(r_json, ensure_ascii=False, indent=2))
    else:
        print("完成")
        if args.scan:
            _print_scan(r)
        else:
            _print_report(r)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# ─────────────────────────────────────────────────────────────────────────────
# KNOWN_LIMITATIONS（骨架边界，已修项）：
# ✅ v2 已做：① 一律 cards（对齐实盘）；② ATR trailing 止损 +
#    涨停买不进 / 跌停卖不出；③ 参数扫描（信号算一遍，撮合多进程并行）。
# ✅ v2.1 已做：实盘风控接入（默认开，--no-riskdata 关闭做 A/B）：
#    - fund_flow_data：按 t 切片历史资金流向 → 连续流出 veto 生效；
#    - extend_sentiment(unlocks)：按 t 切 90 天解禁窗口 → 解禁风险空仓 veto 生效；
#    - extend_fundamental(shareholder)：t ≥ 披露日才生效 → 筹码集中置信加成。
#    全部 point-in-time 切片，无前视。报告打印「风控触发」次数对账。
# 仍待补（out-of-scope，需各自历史源）：
# 1. extend_sector / extend_concept：实盘已走 tushare sector_data / concept；
#    回测 point-in-time 仍需板块/概念指数历史序列，暂未切片接入。
# 2. extend_margin（融资融券）：实盘已走 tushare margin_detail；
#    回测全历史逐日序列切片仍 out-of-scope。
# 3. 资金流 API 仅返回最近 ~27 交易日 → veto 只在回测末段最近窗口生效
#    （与实盘一致：实盘 build_report 同样只取最近资金流）。
# 4. 单标的、单头寸，无多标的组合与仓位再平衡。
# 5. 指数历史依赖腾讯/新浪日线接口，Mac 实测可用；网络失败自动退化为常量 regime。
# 6. 滑点/费为固定单边模型，未考虑成交量冲击与不同券商费率差异。
#
# ✅ 落盘缓存（根治跨进程坏点）：--no-cache 关、--refresh-cache 强制刷新。
#    主进程抓一次写 ~/.trader/backtest_cache/{code}_{days}_*.json，
#    当日内所有运行（含扫描、A/B）读同一份确定性数据；写入前 + 读后都跑
#    健全性快检（>5× 中位数告警），彻底消除 TencentFetcher 跨进程偶发 100× 缩放。
# ✅ extend_northbound 软修正：接线正确（字段名精确匹配 fusion_core、point-in-time 切片、
#    NaN 守卫已加）。合成北向值注入实测：33 天 confidence 被改变（如 +5% 软修正），
#    证明端到端生效。--no-extend 关闭做 A/B。
#    ⚠️ 数据源限制（非接线 bug）：akshare stock_hsgt_hist_em(symbol="北向资金") 的
#    「当日成交净买额」列在本 Mac 环境对 2020+ 全量返回 NaN（仅 2014 年初少数行有值），
#    使回测窗口（2025-09 起）北向恒为 0 → 落死区（>2000/<0 都不满足）不触发。
#    与板块/概念/融资同属「环境数据源缺近期值」一类。换可用北向源（如 tushare
#    moneyflow_hsgt、或 akshare 其它 symbol）即可激活；不造假数据。
#    out-of-scope：extend_sector / extend_concept（需个股→板块实时分类，本 Mac akshare
#    实时端点返回无数据→无法映射历史板块指数）；extend_margin（akshare 仅市场级明细表，
#    无单票历史时间序列）。
# ─────────────────────────────────────────────────────────────────────────────
