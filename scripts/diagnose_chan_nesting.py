#!/usr/bin/env python3
"""日线 + 30m 区间套验证（独立脚本，不改生产代码）。

核心问题：日线一/二类买点或底背驰，经 30m 同价位/同时点确认后，
是否更能过滤假信号、提升命中率？

做法（对称"截至日期 d"快照）：
  1) 对每只标的，在 30m 覆盖窗口内（约 2026-03-01 ~ 2026-07-13）按 step 个交易日
     取"截至日期 d"的日线前缀，跑 chanlun → 得日线买点/底背驰信号(价=当日收盘)。
  2) 同日期 d 截断 30m 前缀，跑 chanlun → 检查 30m 是否在相近价位出现
     一/二类买(或类二买)或底背驰，作为"区间套确认"。
  3) 记录该日线信号：是否被 30m 确认 + 其后 +10 交易日前向收益。
  4) 统计：确认组 vs 未确认组 的前向收益(均值/胜率/中位数)，并做
     "日线-only" vs "日线+30m嵌套" 两策略对比。

数据源：新浪(沙箱放行)。30m datalen=800 覆盖约 5 个月(2026-02-10~07-14)。
用法：
  # 先联网拉 30m（带重试落盘 chan_csv_30m/）
  PYTHONPATH=02-共享模块-shared:01-功能包-packages/trader/scripts \\
    python scripts/diagnose_chan_nesting.py --fetch
  # 离线跑验证（--csv-dir 可选，默认读 scripts/chan_csv + chan_csv_30m）
  PYTHONPATH=02-共享模块-shared:01-功能包-packages/trader/scripts \\
    python scripts/diagnose_chan_nesting.py
  # 单标的冒烟测试：--symbol 688248.SH --step 5
"""
import os
import sys
import csv
import time
import argparse
import requests

ROOT = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(ROOT)
sys.path.insert(0, os.path.join(PARENT, "02-共享模块-shared"))
sys.path.insert(0, os.path.join(PARENT, "01-功能包-packages/trader/scripts"))

from trader_shared.chan_core import chanlun_analysis  # noqa: E402

DAILY_DIR = os.path.join(ROOT, "chan_csv")       # 既有日线 CSV
LOWER_DIR = os.path.join(ROOT, "chan_csv_30m")    # 新拉 30m CSV
os.makedirs(LOWER_DIR, exist_ok=True)

SYMBOLS = [
    ("600036.SH", "招商银行(银行)"),
    ("000001.SZ", "平安银行(银行)"),
    ("601318.SH", "中国平安(保险)"),
    ("600030.SH", "中信证券(券商)"),
    ("601857.SH", "中石油(能源)"),
    ("600900.SH", "长江电力(电力)"),
    ("600276.SH", "恒瑞医药(医药)"),
    ("300760.SZ", "迈瑞医疗(医疗)"),
    ("603259.SH", "药明康德(CXO)"),
    ("688981.SH", "中芯国际(半导体)"),
    ("002475.SZ", "立讯精密(电子)"),
    ("002594.SZ", "比亚迪(新能源整车)"),
    ("600519.SH", "贵州茅台(白酒)"),
    ("000858.SZ", "五粮液(白酒)"),
    ("600887.SH", "伊利股份(食品)"),
    ("603288.SH", "海天味业(调味品)"),
    ("300750.SZ", "宁德时代(电池)"),
    ("601012.SH", "隆基绿能(光伏)"),
    ("300274.SZ", "阳光电源(逆变器)"),
    ("601899.SH", "紫金矿业(有色)"),
    ("600309.SH", "万华化学(化工)"),
    ("600019.SH", "宝钢股份(钢铁)"),
    ("600760.SH", "中航沈飞(军工)"),
    ("000333.SZ", "美的集团(家电)"),
    ("000651.SZ", "格力电器(家电)"),
    ("601633.SH", "长城汽车(汽车)"),
    ("000002.SZ", "万科A(地产)"),
    ("600941.SH", "中国移动(通信)"),
    ("600031.SH", "三一重工(机械)"),
    ("688248.SH", "南网科技(科创储能)"),
]

SIGNAL_START = "20260301"   # 30m 起始 02-10，留 1 月前缀余量
SIGNAL_END = "20260713"
FWD_BARS = 10               # 前向收益窗口(交易日)
PRICE_TOL = 0.03           # 30m 确认买点价位容差
MIN_LOWER_BARS = 60        # 30m 前缀最短(否则无法判定)


def _sina_symbol(code):
    num, market = code.split(".")
    return ("sh" if market == "SH" else "sz") + num


# ───────────────────────── 数据加载 ─────────────────────────
def load_csv(path):
    bars = []
    with open(path, encoding="utf-8") as f:
        next(f)
        for line in f:
            x = line.strip().split(",")
            if len(x) < 6:
                continue
            bars.append({
                "date": x[0], "open": float(x[1]), "close": float(x[2]),
                "high": float(x[3]), "low": float(x[4]), "volume": float(x[5]),
            })
    return bars


def load_daily(code):
    return load_csv(os.path.join(DAILY_DIR, code + ".csv"))


def fetch_30m(code, force=False):
    cache = os.path.join(LOWER_DIR, code + ".csv")
    if os.path.exists(cache) and not force:
        return load_csv(cache)
    sym = _sina_symbol(code)
    url = ("https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
           f"CN_MarketData.getKLineData?symbol={sym}&scale=30&ma=no&datalen=800")
    rows = None
    for attempt in range(8):
        try:
            r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
            rows = r.json()
            if rows:
                break
        except Exception:
            time.sleep(2)
    if not rows:
        print(f"  [30m] {code} 拉取失败")
        return []
    with open(cache, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["日期", "开盘价", "收盘价", "最高价", "最低价", "成交量"])
        for d in rows:
            dt = str(d.get("day", "")).replace("-", "")[:8]
            w.writerow([dt, d["open"], d["close"], d["high"], d["low"], d["volume"]])
    return load_csv(cache)


def trunc(bars, d):
    return [b for b in bars if b["date"] <= d]


# ───────────────────────── 信号判定 ─────────────────────────
def daily_signal(bars_prefix):
    """返回截至前缀的日线信号。出错返回 None。"""
    if len(bars_prefix) < 50:
        return None
    try:
        res = chanlun_analysis(bars_prefix, current=bars_prefix[-1]["close"],
                               symbol="X", timeframe="daily")
    except Exception as e:
        return {"error": str(e)[:60]}
    bps = res.get("buy_points", []) or []
    div = res.get("divergence", {}) or {}
    types = [bp["type"] for bp in bps]
    return {
        "has_buy": bool(bps),
        "types": types,
        "bottom_div": bool(div.get("bottom_divergence")),
        "price": bars_prefix[-1]["close"],
        "structure": res.get("structure_type"),
    }


def lower_confirm(lower_prefix, daily_price):
    """30m 前缀是否在区间套价位确认日线信号。"""
    if len(lower_prefix) < MIN_LOWER_BARS:
        return False, "前缀过短"
    try:
        res = chanlun_analysis(lower_prefix, current=lower_prefix[-1]["close"],
                               symbol="X", timeframe="30m")
    except Exception:
        return False, "30m异常"
    bps = res.get("buy_points", []) or []
    div = res.get("divergence", {}) or {}
    for bp in bps:
        if bp["type"] in ("一类买", "二类买", "类二买"):
            if abs(bp["price"] - daily_price) / daily_price <= PRICE_TOL:
                return True, bp["type"]
    if div.get("bottom_divergence"):
        return True, "底背驰"
    return False, None


# ───────────────────────── 主流程 ─────────────────────────
def collect_dates(daily, step):
    ds = [b["date"] for b in daily if SIGNAL_START <= b["date"] <= SIGNAL_END]
    return ds[::step]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true", help="联网拉 30m 并落盘")
    ap.add_argument("--symbol", default=None, help="仅测单标的(冒烟)")
    ap.add_argument("--step", type=int, default=10, help="取样步长(交易日)")
    args = ap.parse_args()

    symbols = [s for s in SYMBOLS if (args.symbol is None or s[0] == args.symbol)]
    if args.fetch:
        print("=== 拉取 30m ===")
        for code, label in symbols:
            bars = fetch_30m(code)
            print(f"  {label} {code}: {len(bars)} 条 30m")

    rows = []          # 每条日线信号记录
    snap = []          # 当前快照
    for code, label in symbols:
        daily = load_daily(code)
        lower = fetch_30m(code) if os.path.exists(os.path.join(LOWER_DIR, code + ".csv")) else []
        if not daily:
            continue
        # 当前快照(全量)
        ds_now = daily_signal(daily)
        if ds_now and (ds_now.get("has_buy") or ds_now.get("bottom_div")):
            conf, ctype = (lower_confirm(lower, ds_now["price"]) if lower else (False, "无30m"))
            snap.append((label, code, ds_now["types"], ds_now["bottom_div"],
                         conf, ctype, ds_now["price"], ds_now["structure"]))
        # 历史取样
        dates = collect_dates(daily, args.step)
        for d in dates:
            pre = trunc(daily, d)
            ds = daily_signal(pre)
            if not ds or (not ds.get("has_buy") and not ds.get("bottom_div")):
                continue
            # 前向收益
            idx = next((i for i, b in enumerate(daily) if b["date"] == d), None)
            fwd = None
            if idx is not None and idx + FWD_BARS < len(daily):
                fwd = daily[idx + FWD_BARS]["close"] / daily[idx]["close"] - 1.0
            conf, ctype = (lower_confirm(trunc(lower, d), ds["price"])
                           if lower else (False, "无30m"))
            rows.append({
                "code": code, "date": d,
                "types": ",".join(ds["types"]) or ("底背驰" if ds["bottom_div"] else ""),
                "confirmed": conf, "ctype": ctype or "",
                "price": ds["price"], "fwd": fwd,
            })

    # ── 统计 ──
    print(f"\n=== 区间套验证结果 (step={args.step}, 前向{FWD_BARS}日) ===")
    print(f"日线买点/底背驰信号样本: {len(rows)}")
    conf_rows = [r for r in rows if r["confirmed"]]
    unconf_rows = [r for r in rows if not r["confirmed"]]
    print(f"  经 30m 确认: {len(conf_rows)} | 未确认: {len(unconf_rows)}")

    def _stat(group, name):
        fwd = [r["fwd"] for r in group if r["fwd"] is not None]
        if not fwd:
            print(f"  [{name}] 样本(有前向收益)=0")
            return
        avg = sum(fwd) / len(fwd)
        hit = sum(1 for x in fwd if x > 0) / len(fwd)
        med = sorted(fwd)[len(fwd) // 2]
        print(f"  [{name}] n={len(fwd)} 均值={avg*100:+.2f}% 胜率={hit*100:.1f}% 中位={med*100:+.2f}%")

    print("  前向收益对比:")
    _stat(conf_rows, "30m确认组")
    _stat(unconf_rows, "未确认组")
    _stat(rows, "全部日线信号")

    # 策略对比：日线-only vs 日线+30m嵌套
    print("\n  策略对比(同等信号触发):")
    print(f"    日线-only : 交易数={len(rows)} ", end="")
    _brief(rows)
    print(f"    嵌套确认  : 交易数={len(conf_rows)} ", end="")
    _brief(conf_rows)

    # 当前快照
    if snap:
        print("\n=== 当前快照(截至 2026-07-14) 日线信号 + 30m 确认 ===")
        for label, code, types, bdiv, conf, ctype, price, struct in snap:
            sig = ",".join(types) + ("+底背驰" if bdiv else "")
            print(f"  {label:18s} {code} 日线[{sig}] 价={price:.2f} 30m确认={conf} {ctype}")

    # 明细(确认组样例)
    print("\n=== 确认组样例(前15) ===")
    for r in conf_rows[:15]:
        print(f"  {r['code']} {r['date']} {r['types']:12s} 30m={r['ctype']:6s} 价={r['price']:.2f} 前向={'' if r['fwd'] is None else (r['fwd']*100>0 and '+' or '')+str(round(r['fwd']*100,2))+'%'}")


def _brief(group):
    fwd = [r["fwd"] for r in group if r["fwd"] is not None]
    if fwd:
        avg = sum(fwd) / len(fwd)
        hit = sum(1 for x in fwd if x > 0) / len(fwd)
        print(f"均值={avg*100:+.2f}% 胜率={hit*100:.1f}%")
    else:
        print("无前向收益样本")


if __name__ == "__main__":
    main()
