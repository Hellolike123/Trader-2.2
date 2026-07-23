# -*- coding: utf-8 -*-
"""日内 (T0) 无前视回测引擎。

复用 t0 skill 的真实信号脑 (price_point_engine.build_price_point_model) 做日内 T+0 回放。
设计目标：与日线回测引擎 (backtest_engine.py) 并列，用户"两个都要用"。

无前视保证 (关键，逐条对应代码)：
1. signal_fn(t) 只喂 all_5m[:t_idx+1] / daily_bars 中日期 < D / 15m 中 dt <= now；
   build_price_point_model 内部再经 completed_5m_bars(now) 切掉 >=now 的棒 -> 决策只用 t 之前数据。
2. 合成 quote 的 今日高低 由「已完成切片」算 (非全天)，避免前视。
3. pre_close 取 t 前一交易日的日线收盘。
4. chan_5m / chan_15m 均用切片棒 + current=close_t 计算，非全天。
5. 撮合发生在 t 之后的真实棒价 (限价单等待成交)，不参与决策 -> 合法。

与实盘差异 (诚实边界，详见文件尾部 KNOWN_LIMITATIONS)：
- 无 tick 大单验证 (回测无 tick 数据)，仅跳过该增强。
- 5m 历史受数据源限制：Sina getKLineData 仅返回最近 ~2400 根 5m (≈50 交易日)。
- 涨跌停约束：买价 >= 涨停价 不买；卖价 <= 跌停价 不卖。
- 日内专用资金，收盘强平 (T+0 不隔夜)。
"""

from __future__ import annotations

import sys
import os
import json
import glob
import bisect
import argparse
import subprocess
import tempfile
import gc
from datetime import datetime, timedelta
from typing import Any

# 02-共享模块-shared 的绝对路径 (trader_shared 包所在目录)，供子进程 PYTHONPATH。
SHARED_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── 注入 t0 skill 脚本目录，使 import 解析到「与实盘 t0 同一份」信号脑/ trader_shared ──
T0_DIR = os.path.expanduser("~/.workbuddy/skills/t0/scripts")
if os.path.isdir(T0_DIR) and T0_DIR not in sys.path:
    sys.path.insert(0, T0_DIR)

from trader_shared.light_data import _fetch_mins_fallback, resolve_security  # noqa: E402
from trader_shared.fetchers import TencentFetcher  # noqa: E402
from price_point_engine import build_price_point_model, completed_5m_bars  # noqa: E402
from trader_shared.structure_core import build_structure_context  # noqa: E402
# 注：2026-07-23 起 t0 三重共振第一席位 = Al Brooks 价格行为（analyze_ab，
# build_price_point_model 内部自算），缠论 chan_5m/chan_15m 不再消费，已裁掉。


# ── 撮合/费用参数 ───────────────────────────────────────────────
COMMISSION = 0.00025      # 万 2.5 双边
STAMP = 0.001             # 印花税 仅卖
SLIP_BUY = 0.001          # 买方向滑点 (限价单劣化成交)
SLIP_SELL = 0.001         # 卖方向滑点
INTRADAY_FRACTION = 0.2     # 单笔占日内资金比例
LOT = 100                  # 一手
MAX_RT_PER_DAY = 3          # 每日最多回合交易数 (防过度交易噪声)
PLAN_EVERY = 1             # 每 N 根 5m 棒评估一次 plan (1=每棒)


def _cache_dir() -> str:
    d = os.path.expanduser("~/.trader/intraday_cache")
    os.makedirs(d, exist_ok=True)
    return d


def _today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _cache_path(code: str) -> str:
    return os.path.join(_cache_dir(), f"{code}.json")


def _sanity_bars(bars: list[dict], label: str) -> bool:
    """写前+读后双重健全性：剔除收盘价 >5× 中位数的坏点。"""
    if not bars:
        return False
    closes = [float(b.get("close") or 0) for b in bars if b.get("close")]
    if not closes:
        return False
    closes.sort()
    med = closes[len(closes) // 2]
    if med <= 0:
        return False
    bad = [c for c in closes if c > med * 5]
    if bad:
        print(f"[warn] {label} 健全性未过：{len(bad)} 根异常棒(>5×中位数)，丢弃该缓存")
        return False
    return True


def _load_cache(code: str) -> dict | None:
    p = _cache_path(code)
    if not os.path.exists(p):
        return None
    try:
        d = json.load(open(p, "r", encoding="utf-8"))
        if not isinstance(d, dict):
            return None
        if not _sanity_bars(d.get("bars_5m") or [], "bars_5m"):
            return None
        if not _sanity_bars(d.get("bars_15m") or [], "bars_15m"):
            return None
        # 旧缓存也可能缺午休边界棒 -> 读时补（幂等：已补过则不重复）
        d["bars_5m"] = _fix_lunch_gap(d.get("bars_5m") or [], "5m")
        d["bars_15m"] = _fix_lunch_gap(d.get("bars_15m") or [], "15m")
        print(f"[cache] 命中 {code} 缓存 | 5m {len(d.get('bars_5m') or [])} 根 / 15m {len(d.get('bars_15m') or [])} 根 / 日线 {len(d.get('daily') or [])} 根")
        return d
    except Exception:
        return None


def _save_cache(code: str, daily, bars_5m, bars_15m) -> None:
    if not _sanity_bars(bars_5m, "bars_5m"):
        print("[warn] 5m 不健全，不写缓存")
        return
    if not _sanity_bars(bars_15m, "bars_15m"):
        print("[warn] 15m 不健全，不写缓存")
        return
    payload = {
        "fetch_date": _today_str(),
        "daily": daily,
        "bars_5m": bars_5m,
        "bars_15m": bars_15m,
    }
    try:
        json.dump(payload, open(_cache_path(code), "w", encoding="utf-8"), ensure_ascii=False)
        print(f"[cache] 已写 {code} 缓存")
    except Exception as e:
        print(f"[warn] 写缓存失败: {e}")


def load_data(code: str, use_cache: bool = True, force_refresh: bool = False):
    """返回 (daily, bars_5m, bars_15m, sec, cache_used)。"""
    sec = resolve_security(code)
    if use_cache and not force_refresh:
        c = _load_cache(code)
        if c:
            return c["daily"], c["bars_5m"], c["bars_15m"], sec, True
    # 日线 (带 atr14/atr_ratio，供 plan 消费)
    daily = TencentFetcher().fetch_qfq_daily(code, days=400)
    # 5m / 15m 历史：Sina getKLineData 仅返回最近 N 根 (≈50 / 100 交易日)
    bars_5m = _fetch_mins_fallback(sec, "5m", 2400) or []
    bars_15m = _fetch_mins_fallback(sec, "15m", 2400) or []
    bars_5m = _clean_min(bars_5m, "5m")
    bars_15m = _clean_min(bars_15m, "15m")
    # 补 Sina 午休边界缺棒 (13:00)，避免下午 data_status=degraded 误杀
    bars_5m = _fix_lunch_gap(bars_5m, "5m")
    bars_15m = _fix_lunch_gap(bars_15m, "15m")
    _save_cache(code, daily, bars_5m, bars_15m)
    return daily, bars_5m, bars_15m, sec, False


def _clean_min(bars: list[dict], label: str) -> list[dict]:
    out = []
    for b in bars:
        if not b:
            continue
        c = b.get("close")
        if c is None:
            continue
        out.append(b)
    out.sort(key=lambda x: str(x.get("time") or x.get("date") or ""))
    return out


def parse_dt(s: Any) -> datetime | None:
    if not s:
        return None
    s = str(s)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            pass
    return None


def _fix_lunch_gap(bars: list[dict], label: str) -> list[dict]:
    """Sina 5m/15m 历史常缺 13:00 这根（午休后首根被标成 13:05/13:15）。

    后果：下午任意一根棒经 completed_5m_bars 切片后，last 完成棒停在 11:30，
    距 now(>=13:05) > 12min -> data_status='degraded' -> 观察价失效 -> 全下午无交易。
    修法：侦测 11:30 -> 13:05(+N) 的午休跳变，在中间补一根 13:00 棒
    （OHLC 由相邻 AM 收盘 / PM 开盘 插值，volume 平分），恢复标准交易时段结构。
    该修复无前视污染：只补「本就该存在」的午休边界棒，OHLC 取两端真实值。
    """
    if not bars:
        return bars
    out: list[dict] = []
    prev = None
    for b in bars:
        t = parse_dt(b.get("time") or b.get("date"))
        if prev is not None and t is not None:
            pdt = parse_dt(prev.get("time") or prev.get("date"))
            if pdt is not None:
                gap = (t - pdt).total_seconds() / 60
                # 午休跳变：前一棒 11:30 且下一根已是午后首棒(13:05/13:15)，
                # 说明 13:00 这根确实缺失（Sina 特征）-> 补。幂等：一旦补过，
                # 11:30 下一根变成 13:00（不在目标集合）即不再触发。
                phhmm = pdt.strftime("%H:%M")
                thhmm = t.strftime("%H:%M")
                if phhmm == "11:30" and thhmm in ("13:05", "13:15") and gap >= 90:
                    synth = {
                        "time": pdt.date().isoformat() + " 13:00:00",
                        "date": pdt.date().isoformat(),
                        "open": float(prev.get("close") or 0),
                        "close": float(b.get("open") or b.get("close") or 0),
                        "high": max(float(prev.get("close") or 0), float(b.get("open") or 0)),
                        "low": min(float(prev.get("close") or 0), float(b.get("open") or 0)),
                        "amount": (float(b.get("amount") or 0)) / 2.0,
                        "_synth_lunch": True,
                    }
                    vol = float(b.get("volume") or 0) / 2.0
                    synth["volume"] = vol
                    out.append(synth)
        out.append(b)
        prev = b
    n_synth = sum(1 for b in out if b.get("_synth_lunch"))
    if n_synth:
        print(f"[fix] {label} 补 {n_synth} 根午休边界棒(13:00)")
    return out


def board_limit(code: str) -> float:
    c = str(code).upper()
    if c.startswith("688") or c.startswith("689"):
        return 0.20
    if c.startswith("300"):
        return 0.20
    if c[0] in "84" or c.startswith("8") or c.startswith("4"):
        return 0.30
    return 0.10


# 上下文窗口上限：对齐实盘 t0 的 datalen=800，且把 chan 计算复杂度锁在常数。
CTX_5M = 400     # 5m 上下文棒数 (Al Brooks 结构，~8 交易日足够)
CTX_15M = 400    # 15m 上下文棒数 (~33 交易日)


def make_signal_fn(code: str, sec, bars_5m: list[dict], bars_15m: list[dict],
                  daily: list[dict], use_structure: bool = True):
    """闭包：给定 5m 棒全局下标 t_idx，返回无前视的 t0 plan。

    use_structure=True 时，按 t0 设计（t0_run.py "T0-1 fix"）注入 trader 日线
    结构支撑/阻力 (build_structure_context, 用 D 之前日线 = 无前视)，使买/卖区
    宽到日线级；否则退化为仅日内近价位（net_space 常为负 -> 几乎不触发）。
    """
    m15_dt = [parse_dt(b.get("time") or b.get("date")) for b in bars_15m]
    daily_dates = [str(b.get("date") or "") for b in daily]

    def signal_fn(t_idx: int):
        now_bar = bars_5m[t_idx]
        now = parse_dt(now_bar.get("time") or now_bar.get("date")) or datetime.now()
        cur = float(now_bar.get("close") or 0)
        hi5 = max(0, t_idx - CTX_5M + 1)
        kline_5m = bars_5m[hi5: t_idx + 1]  # 模型内部 completed_5m_bars(now) 再切
        completed = completed_5m_bars(kline_5m, now)
        today = now.date().isoformat()
        today_bars = [b for b in completed if str(b.get("time") or b.get("date") or "").startswith(today)]
        if today_bars:
            hi = max(float(b["high"]) for b in today_bars if b.get("high") is not None)
            lo = min(float(b["low"]) for b in today_bars if b.get("low") is not None)
            op = float(today_bars[0].get("open") or today_bars[0].get("close") or 0)
        else:
            hi = lo = op = cur
        di = bisect.bisect_left(daily_dates, today)
        daily_upto = daily[:di]
        pre_close = float(daily_upto[-1]["close"]) if daily_upto else None
        quote = {
            "name": getattr(sec, "name", code),
            "symbol": code,
            "high": hi,
            "low": lo,
            "open": op,
            "price": cur,
            "current_price": cur,
            "pre_close": pre_close,
            "data_status": "full",
        }
        n15 = sum(1 for dt in m15_dt if dt is not None and dt <= now)
        lo15 = max(0, n15 - CTX_15M)
        sub15 = bars_15m[lo15: n15]
        report_data = {
            "quote": quote,
            "daily_bars": daily_upto,
            "kline_5m": kline_5m,
            "kline_15m": sub15,
            "current_price": cur,
            "now": now,
            "tick_data": [],
            "order_book": None,
        }
        # t0 设计：注入 trader 日线结构支撑/阻力（用 D 之前日线 = 无前视）
        structure_result = None
        if use_structure:
            try:
                structure_result = build_structure_context(
                    cur, daily_upto, change_pct=None, quote=quote)
            except Exception:
                structure_result = None
        model = build_price_point_model(report_data, structure_result=structure_result)
        return model, now_bar

    return signal_fn


def size_qty(capital: float, price: float) -> int:
    if price <= 0:
        return 0
    q = int(capital * INTRADAY_FRACTION / price // LOT) * LOT
    return max(q, 0)


def run_one_day(code: str, day: str, capital: float, plan_every: int,
                use_cache: bool = True, force_refresh: bool = False,
                use_structure: bool = True) -> dict:
    """只处理「单交易日」，在独立子进程里跑以保证 t0 大脑内存可回收。

    返回紧凑结果 dict，由父进程聚合成权益曲线与绩效。
    T+0 当日开平，所以 day_pnl 是自洽的，父进程直接累加即可。
    """
    daily, bars_5m, bars_15m, sec, _ = load_data(code, use_cache, force_refresh)
    signal_fn = make_signal_fn(code, sec, bars_5m, bars_15m, daily,
                                  use_structure=use_structure)
    lim = board_limit(code)
    idxs = [i for i, b in enumerate(bars_5m)
            if (b.get("time") or b.get("date") or "").split(" ")[0] == day]

    res_base = {
        "day": day, "lim": lim, "n_bars": len(idxs), "n_eval": 0,
        "day_pnl": 0.0, "trades": 0, "rt": 0, "wins": 0,
        "pf_num": 0.0, "pf_den": 0.0,
        "n_buy_opp": 0, "n_sell_opp": 0,
        "status_counts": {}, "last_close": 0.0,
        "skipped": len(idxs) < 20,
    }
    if len(idxs) < 20:
        return res_base

    di = bisect.bisect_left([str(b.get("date") or "") for b in daily], day)
    pre = float(daily[di - 1]["close"]) if di > 0 else None
    limit_up = pre * (1 + lim) if pre else 1e9
    limit_dn = pre * (1 - lim) if pre else 0.0

    pos = 0
    entry = 0.0
    day_pnl = 0.0
    rt = 0
    trades = 0
    wins = 0
    pf_num = 0.0
    pf_den = 0.0
    n_eval = 0
    n_buy_opp = 0
    n_sell_opp = 0
    status_counts: dict[str, int] = {}

    for k, gi in enumerate(idxs):
        if plan_every > 1 and (k % plan_every != 0):
            continue
        model, _ = signal_fn(gi)
        n_eval += 1
        buy = model.get("buy") or {}
        sell = model.get("sell") or {}
        res = model.get("resonance") or {}
        buy_green = bool(res.get("buy_green"))
        sell_red = bool(res.get("sell_red"))
        bstat = buy.get("status")
        sstat = sell.get("status")
        status_counts["B:" + str(bstat)] = status_counts.get("B:" + str(bstat), 0) + 1
        status_counts["S:" + str(sstat)] = status_counts.get("S:" + str(sstat), 0) + 1
        # 买 (空仓 + 已触发 + 绿灯 + 不在涨停)
        if pos == 0 and rt < MAX_RT_PER_DAY:
            be = buy.get("execution_price")
            if bstat == "已触发" and buy_green and be is not None:
                be = float(be)
                if be < limit_up:
                    for j in range(k + 1, len(idxs)):
                        low = float(bars_5m[idxs[j]].get("low") or 0)
                        if low <= be * (1 + SLIP_BUY):
                            fill = be * (1 + SLIP_BUY)
                            q = size_qty(capital, fill)
                            if q <= 0:
                                break
                            pos = q
                            entry = fill
                            day_pnl -= fill * q * COMMISSION
                            n_buy_opp += 1
                            break
        # 卖 (持仓 + 已触发 + 红灯 + 不在跌停)
        elif pos > 0:
            se = sell.get("execution_price")
            if sstat == "已触发" and sell_red and se is not None:
                se = float(se)
                if se > limit_dn:
                    for j in range(k + 1, len(idxs)):
                        high = float(bars_5m[idxs[j]].get("high") or 0)
                        if high >= se * (1 - SLIP_SELL):
                            fill = se * (1 - SLIP_SELL)
                            proceeds = fill * pos * (1 - COMMISSION - STAMP)
                            cost = entry * pos * (1 + COMMISSION)
                            pnl = proceeds - cost
                            day_pnl += pnl
                            trades += 1
                            rt += 1
                            if pnl >= 0:
                                wins += 1
                            pf_num += max(pnl, 0.0)
                            pf_den += max(-pnl, 0.0)
                            pos = 0
                            entry = 0.0
                            n_sell_opp += 1
                            break
        # 每根棒后清理 transient，避免子进程内堆积
        if (k % 8 == 0):
            gc.collect()
    # 收盘强平
    if pos > 0:
        last_close = float(bars_5m[idxs[-1]].get("close") or 0)
        proceeds = last_close * pos * (1 - COMMISSION - STAMP)
        cost = entry * pos * (1 + COMMISSION)
        pnl = proceeds - cost
        day_pnl += pnl
        trades += 1
        rt += 1
        if pnl >= 0:
            wins += 1
        pf_num += max(pnl, 0.0)
        pf_den += max(-pnl, 0.0)
        pos = 0
        n_sell_opp += 1
    last_close = float(bars_5m[idxs[-1]].get("close") or 0)

    return {
        "day": day, "lim": lim, "n_bars": len(idxs), "n_eval": n_eval,
        "day_pnl": day_pnl, "trades": trades, "rt": rt, "wins": wins,
        "pf_num": pf_num, "pf_den": pf_den,
        "n_buy_opp": n_buy_opp, "n_sell_opp": n_sell_opp,
        "status_counts": status_counts, "last_close": last_close,
        "skipped": False,
    }


def run_backtest(code: str, capital: float = 100000.0, use_cache: bool = True,
                force_refresh: bool = False, plan_every: int = PLAN_EVERY,
                use_structure: bool = True):
    """协调器：每天起一个独立子进程跑 run_one_day，避免 t0 大脑内存累计 OOM。

    子进程每跑完一天即退出，内存回收；父进程只做聚合。
    """
    # 父进程仅读一次缓存/抓数，枚举交易日（用于 --refresh-cache 时只抓一次）。
    daily, bars_5m, bars_15m, sec, cache_used = load_data(code, use_cache, force_refresh)
    if not bars_5m:
        print("[error] 无 5m 数据，无法回测")
        return None

    day_idx: dict[str, list[int]] = {}
    for i, b in enumerate(bars_5m):
        d = (b.get("time") or b.get("date") or "").split(" ")[0]
        day_idx.setdefault(d, []).append(i)
    days = [d for d in sorted(day_idx.keys()) if len(day_idx[d]) >= 20]

    py = sys.executable
    env = dict(os.environ)
    env["PYTHONPATH"] = SHARED_DIR
    script = os.path.abspath(__file__)

    equity = capital
    equity_curve: list[float] = [equity]
    trades = 0
    wins = 0
    pf_num = 0.0
    pf_den = 0.0
    rt_total = 0
    daily_pnls: list[float] = []
    first_day = last_day = None
    status_total: dict[str, int] = {}
    total_buy_opp = 0
    total_sell_opp = 0
    total_eval = 0

    for D in days:
        if first_day is None:
            first_day = D
        last_day = D
        out = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False,
            prefix=f"ibt_{code}_{D}_")
        out_path = out.name
        out.close()
        cmd = [py, script, "--target", code, "--worker-day", D,
               "--capital", str(capital), "--plan-every", str(plan_every),
               "--worker-out", out_path]
        if not use_cache:
            cmd.append("--no-cache")
        if not use_structure:
            cmd.append("--no-structure")
        # 注意：--refresh-cache 只在父进程抓一次，子进程一律走缓存，避免重复抓网。
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=900)
            if r.returncode != 0:
                print(f"[warn] {D} 子进程异常 rc={r.returncode}: {r.stderr[-400:]}")
                try:
                    os.unlink(out_path)
                except Exception:
                    pass
                continue
            with open(out_path, "r", encoding="utf-8") as fh:
                res = json.load(fh)
        except Exception as e:
            print(f"[warn] {D} 子进程失败: {e}")
            try:
                os.unlink(out_path)
            except Exception:
                pass
            continue
        finally:
            try:
                os.unlink(out_path)
            except Exception:
                pass
        if res.get("skipped"):
            print(f"[day] {D} 跳过 (棒数={res.get('n_bars')})")
            continue
        equity += res["day_pnl"]
        equity_curve.append(equity)
        daily_pnls.append(res["day_pnl"])
        trades += res["trades"]
        wins += res["wins"]
        pf_num += res["pf_num"]
        pf_den += res["pf_den"]
        rt_total += res["rt"]
        total_buy_opp += res["n_buy_opp"]
        total_sell_opp += res["n_sell_opp"]
        total_eval += res["n_eval"]
        for k, v in res.get("status_counts", {}).items():
            status_total[k] = status_total.get(k, 0) + v
        print(f"[day] {D} pnl={res['day_pnl']:+.0f} rt={res['rt']} "
              f"buyOpp={res['n_buy_opp']} sellOpp={res['n_sell_opp']} bars={res['n_bars']}")

    # 绩效
    n_days = len(equity_curve) - 1
    total_ret = equity / capital - 1.0 if capital else 0.0
    if n_days > 0 and equity / capital > 0:
        ann = (equity / capital) ** (252.0 / n_days) - 1.0
    else:
        ann = 0.0
    # 夏普 (基于每日盈亏)
    if len(daily_pnls) > 1:
        mean = sum(daily_pnls) / len(daily_pnls)
        var = sum((x - mean) ** 2 for x in daily_pnls) / (len(daily_pnls) - 1)
        std = var ** 0.5
        sharpe = (mean / std * (252 ** 0.5)) if std > 0 else 0.0
    else:
        sharpe = 0.0
    # 最大回撤
    peak = equity_curve[0]
    max_dd = 0.0
    for e in equity_curve:
        if e > peak:
            peak = e
        dd = (e / peak - 1.0) if peak > 0 else 0.0
        if dd < max_dd:
            max_dd = dd
    win_rate = (wins / trades) if trades else 0.0
    profit_factor = (pf_num / pf_den) if pf_den > 0 else (float("inf") if pf_num > 0 else 0.0)

    return {
        "code": code,
        "capital": capital,
        "first_day": first_day,
        "last_day": last_day,
        "n_days": n_days,
        "equity": equity,
        "total_ret": total_ret,
        "annual": ann,
        "sharpe": sharpe,
        "max_dd": max_dd,
        "trades": trades,
        "rt_total": rt_total,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "cache_used": cache_used,
        "lim_pct": board_limit(code),
        "bars_5m": len(bars_5m),
        "bars_15m": len(bars_15m),
        "total_eval": total_eval,
        "total_buy_opp": total_buy_opp,
        "total_sell_opp": total_sell_opp,
        "status_total": status_total,
    }


def _print_report(r: dict) -> None:
    if r is None:
        return
    eq = r["equity"]
    cap = r["capital"]
    pf = r["profit_factor"]
    pf_s = "inf" if pf == float("inf") else "%.2f" % pf
    lines = []
    lines.append("=" * 60)
    lines.append("日内 T0 无前视回测报告")
    lines.append("=" * 60)
    lines.append("标的            : %s" % r["code"])
    lines.append("窗口            : %s -> %s  (约 %d 交易日)" % (r["first_day"], r["last_day"], r["n_days"]))
    lines.append("5m/15m 数据    : %d / %d 根 (Sina 最近窗口)" % (r["bars_5m"], r["bars_15m"]))
    lines.append("涨跌停板        : +/-%.0f%%" % (r["lim_pct"] * 100))
    lines.append("数据来源        : %s" % ("盘缓存" if r["cache_used"] else "实时抓取"))
    lines.append("-" * 60)
    lines.append("初始资金        : %.0f" % cap)
    lines.append("期末权益        : %.0f" % eq)
    lines.append("总收益          : %+.2f%%" % (r["total_ret"] * 100))
    lines.append("年化收益        : %+.2f%%" % (r["annual"] * 100))
    lines.append("夏普比率        : %.2f" % r["sharpe"])
    lines.append("最大回撤        : %+.2f%%" % (r["max_dd"] * 100))
    lines.append("-" * 60)
    lines.append("回合交易        : %d" % r["rt_total"])
    lines.append("成交笔数        : %d" % r["trades"])
    lines.append("胜率            : %.1f%%" % (r["win_rate"] * 100))
    lines.append("盈亏比          : %s" % pf_s)
    lines.append("-" * 60)
    lines.append("信号评估        : 共 %d 次 / 买触发机会 %d / 卖触发机会 %d"
                 % (r.get("total_eval", 0), r.get("total_buy_opp", 0), r.get("total_sell_opp", 0)))
    st = r.get("status_total") or {}
    if st:
        top = sorted(st.items(), key=lambda kv: -kv[1])[:8]
        lines.append("状态分布(top)   : " + "  ".join("%s=%d" % (k, v) for k, v in top))
    lines.append("=" * 60)
    print("\n".join(lines))


def main():
    ap = argparse.ArgumentParser(description="日内 T0 无前视回测引擎")
    ap.add_argument("--target", required=True, help="标的代码 如 688248")
    ap.add_argument("--capital", type=float, default=100000.0, help="日内专用资金 默认 100000")
    ap.add_argument("--no-cache", action="store_true", help="禁用落盘缓存")
    ap.add_argument("--refresh-cache", action="store_true", help="强制重抓并刷新缓存")
    ap.add_argument("--plan-every", type=int, default=PLAN_EVERY, help="每 N 根 5m 棒评估一次 plan")
    ap.add_argument("--no-structure", action="store_true", help="不注入日线结构支撑/阻力（退化为仅日内近价位）")
    ap.add_argument("--worker-day", default=None, help="(内部)子进程模式：只处理该交易日")
    ap.add_argument("--worker-out", default=None, help="(内部)子进程结果写出 JSON 路径")
    args = ap.parse_args()
    if args.worker_day:
        # 子进程模式：只跑单日，结果写 --worker-out (父进程读取)，并回显 stdout 便于调试。
        res = run_one_day(
            args.target, args.worker_day, capital=args.capital,
            plan_every=args.plan_every,
            use_cache=not args.no_cache, force_refresh=args.refresh_cache,
            use_structure=not args.no_structure)
        if args.worker_out:
            try:
                with open(args.worker_out, "w", encoding="utf-8") as fh:
                    json.dump(res, fh, ensure_ascii=False)
            except Exception as e:
                print(f"[worker] 写结果失败: {e}", file=sys.stderr)
        print(json.dumps(res, ensure_ascii=False))
        return
    r = run_backtest(
        args.target,
        capital=args.capital,
        use_cache=not args.no_cache,
        force_refresh=args.refresh_cache,
        plan_every=args.plan_every,
        use_structure=not args.no_structure,
    )
    _print_report(r)


if __name__ == "__main__":
    main()


# ─────────────────────────────────────────────────────────────────────────────
# KNOWN_LIMITATIONS (诚实边界)
# 1. 5m 历史受数据源限制：Sina getKLineData 仅返回最近 ~2400 根 5m
#    (≈50 交易日)。无法回放更早日期——这是数据源限制，非前视问题。
#    15m 取 2400 根 ≈100 交易日，故回放窗口由 5m 长度决定。
# 2. 无 tick 大单验证：实盘 t0 在靠近关注价时拉 tick 做物理大单确认，
#    回测无 tick 数据，该增强被跳过 (不影响 plan 主体逻辑)。
# 3. 撮合模型：买/卖信号产生后，以限价单在「同日后续 5m 棒」等待成交
#    (买看后续棒 LOW<=买价；卖看后续棒 HIGH>=卖价)，滑点劣化成交；
#    收盘强制平仓 (T+0 不隔夜)。每日最多 MAX_RT_PER_DAY 回合防过度交易。
# 4. 涨跌停约束：买价 >= 涨停价 视为无法买入跳过；卖价 <= 跌停价 跳过。
# 5. 无前视保证见文件头注释逐条；与日线引擎并列，共用 t0 真实信号脑。
# 6. 板块/概念/北向/融资等软修正未接入 (同日报引擎，需各自历史源)。
# 7. 内存隔离：每日起独立子进程跑 run_one_day (跑完即退出回收 t0 大脑内存)，
#    父进程只聚合结果。避免 2400 根 5m 在单进程内累计分配触发 OOM (exit 137)。
#    单日子进程峰值 ~85MB，安全；--refresh-cache 只在父进程抓一次，子进程统一走缓存。
# ─────────────────────────────────────────────────────────────────────────────
