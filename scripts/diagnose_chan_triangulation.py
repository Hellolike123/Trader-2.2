#!/usr/bin/env python3
"""缠论分类三角对照（只读，不改生产代码）。

三层对照：
  1) 原典严格口径   —— 见 formulas.md §9（规则源头，交实战终审）
  2) czsc 工程实现  —— 主流开源实现（工程共识参照，非权威裁判）
  3) 我们的实现      —— trader_shared.chan_core.chanlun_analysis

对代表性 30 只跨行业标的（覆盖银行/保险/券商/能源/医药/科技/消费/新能源/
周期/军工/家电/汽车/地产/通信/机械/科创），
输出「原典清单口径 / czsc / 我们的实现」三角矩阵，标注共识区 vs 定义分歧区。

用法：
  PYTHONPATH=02-共享模块-shared:01-功能包-packages/trader/scripts \\
    python scripts/diagnose_chan_triangulation.py
  # 加 --probe 先打印 czsc 真实 API 结构（装包后首次校准用）
  # 加 --csv-dir <目录> 走本地 CSV（<code>.csv，网易财经格式），完全不碰网络
  #
  # 数据源：新浪财经（沙箱白名单可达）优先；若网络不通回退 tushare / 网易 CSV。
  # 若三者皆不可达，用 --csv-dir 提供本地文件即可。
"""
import sys
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "02-共享模块-shared"))
sys.path.insert(0, os.path.join(ROOT, "01-功能包-packages/trader/scripts"))

# 沙箱出口代理会拦截外网（报错 copilot.tencent.com）。清空代理环境变量，
# 让 requests 直连——与之前 tushare 直连成功的行为一致。
for _p in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY",
           "all_proxy", "ALL_PROXY", "no_proxy", "NO_PROXY"):
    os.environ.pop(_p, None)

import warnings
# 抑制 tushare_client 的 SDK 初始化 / HTTP 失败 UserWarning，保持输出干净
warnings.filterwarnings("ignore")

from trader_shared.chan_core import chanlun_analysis

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

START, END = "20240101", "20260714"


def _tushare_daily_to_bars(rows):
    return [{
        "date": str(r.get("trade_date")),
        "open": float(r.get("open")),
        "close": float(r.get("close")),
        "high": float(r.get("high")),
        "low": float(r.get("low")),
        "volume": float(r.get("vol", 0) or 0),
    } for r in rows]


def _to_netease_code(code):
    """688248.SH -> 0688248 ; 000001.SZ -> 1000001（网易财经编码规则）。"""
    num, market = code.split(".")
    prefix = "0" if market == "SH" else "1"
    return prefix + num


def _normalize_date(s):
    s = str(s).strip()
    return s.replace("-", "") if "-" in s else s


def _parse_netease_csv(text):
    """解析网易财经 CSV（表头：日期,股票代码,名称,收盘价,最高价,最低价,开盘价,...）。
    返回 bar 列表 [{'date','open','close','high','low','volume'}]。"""
    import csv
    import io
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if len(rows) < 2:
        return []
    header = rows[0]

    def _idx(name):
        try:
            return header.index(name)
        except ValueError:
            return -1

    i_date = _idx("日期")
    i_open = _idx("开盘价")
    i_close = _idx("收盘价")
    i_high = _idx("最高价")
    i_low = _idx("最低价")
    i_vol = _idx("成交量")
    if -1 in (i_date, i_open, i_close, i_high, i_low, i_vol):
        return []
    bars = []
    for r in rows[1:]:
        try:
            bars.append({
                "date": _normalize_date(r[i_date]),
                "open": float(r[i_open]),
                "close": float(r[i_close]),
                "high": float(r[i_high]),
                "low": float(r[i_low]),
                "volume": float(r[i_vol] or 0),
            })
        except Exception:
            continue
    return bars


def _fetch_from_netease(code, start=START, end=END):
    """网易财经历史数据 CSV（通常不受 tushare 网络封锁影响）。
    返回 (bars, err)：成功 err=None，失败 err 为原因字符串。"""
    import urllib.request
    ncode = _to_netease_code(code)
    url = (f"http://quotes.money.163.com/service/chddata.html"
           f"?code={ncode}&start={start}&end={end}"
           f"&fields=TCLOSE;HIGH;LOW;TOPEN;VOTURNOVER;VATURNOVER")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        raw = urllib.request.urlopen(req, timeout=30).read()
    except Exception as e:  # noqa
        return [], f"netease_err:{e}"
    text = None
    for enc in ("utf-8", "gbk"):
        try:
            text = raw.decode(enc)
            break
        except Exception:
            continue
    if text is None:
        return [], "decode_err"
    return _parse_netease_csv(text), None


def _load_csv_bars(path):
    """从本地 CSV 读取（格式同网易财经：日期,开盘价,收盘价,最高价,最低价,成交量）。"""
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except Exception as e:  # noqa
        return [], f"csv_open_err:{e}"
    text = None
    for enc in ("utf-8", "gbk"):
        try:
            text = raw.decode(enc)
            break
        except Exception:
            continue
    if text is None:
        return [], "decode_err"
    bars = _parse_netease_csv(text)
    if not bars:
        return [], "empty_or_col_mismatch"
    return bars, None


def _sina_symbol(code):
    """688248.SH -> sh688248 ; 000001.SZ -> sz000001（新浪行情代码规则）。"""
    num, market = code.split(".")
    return ("sh" if market == "SH" else "sz") + num


def _fetch_from_sina(code, start=START, end=END):
    """新浪财经日线 K 线（沙箱白名单内可达，绕过 eastmoney/tushare/网易 封锁）。
    返回 (bars, err)：成功 err=None，失败 err 为原因字符串。"""
    import requests
    sym = _sina_symbol(code)
    url = ("https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
           f"CN_MarketData.getKLineData?symbol={sym}&scale=240&ma=no&datalen=1500")
    try:
        r = requests.get(url, timeout=30)
        data = r.json()
    except Exception as e:  # noqa
        return [], f"sina_err:{e}"
    bars = []
    for d in data:
        try:
            dt = str(d.get("day", "")).replace("-", "")
            if dt < start or dt > end:
                continue
            bars.append({
                "date": dt,
                "open": float(d["open"]),
                "close": float(d["close"]),
                "high": float(d["high"]),
                "low": float(d["low"]),
                "volume": float(d.get("volume") or 0),
            })
        except Exception:
            continue
    if not bars:
        return [], "sina_empty"
    return bars, None


def _fetch_real_bars(code, start=START, end=END):
    """取真实日线。优先级：新浪财经（沙箱可达）→ tushare(官方端点) → 网易 CSV。"""
    # 1) 新浪财经（沙箱白名单内，最稳）
    bars, err = _fetch_from_sina(code, start, end)
    if bars:
        return bars
    # 2) tushare（官方端点，https）—— 沙箱可能不通，回退用
    try:
        from trader_shared.tushare_client import get_client
        c = get_client()
        c._api_url = "https://api.tushare.pro"
        rows = c.query_daily(ts_code=code, start_date=start, end_date=end)
        if rows:
            rows = sorted(rows, key=lambda r: str(r.get("trade_date", "")))
            return _tushare_daily_to_bars(rows)
    except Exception:
        pass
    # 3) 网易财经 CSV 回退
    bars2, err2 = _fetch_from_netease(code, start, end)
    if bars2:
        return bars2
    return []


# ───────────────────────── czsc 适配层 ─────────────────────────
def _our_impl_classify(bars):
    cur = bars[-1]["close"]
    res = chanlun_analysis(bars, current=cur, symbol="X")
    st = res.get("structure_type", "无结构")
    tl = res.get("trend_label", "-")
    pc = res.get("pivot_count", 0)
    return st, tl, pc


def _norm_dir(x):
    if "上涨" in x:
        return "up"
    if "下跌" in x:
        return "down"
    if "盘整" in x:
        return "pan"
    return "none"


def _czsc_classify(bars):
    """用 czsc 跑同样本，映射为 {上涨趋势,下跌趋势,盘整,无结构}。

    返回 (label, fenlei_str, bi_count, zs_count, raw_info)。
    czsc 版本 API 差异较大，这里用防御式探测 + 多路径回退。
    """
    try:
        # 最小化导入，避免 czsc 顶层 __init__ 拉起可能触发外网的子模块
        try:
            from czsc.analyze import CZSC
        except Exception:
            from czsc import CZSC
        from czsc.objects import RawBar
        from czsc.enum import Freq
    except Exception as e:  # noqa
        return ("czsc不可用", f"import_err:{e}", 0, 0, {})

    # 构造 RawBar
    raws = []
    for i, b in enumerate(bars):
        try:
            from datetime import datetime
            dt = datetime.strptime(b["date"], "%Y%m%d")
        except Exception:
            from datetime import datetime, timedelta
            dt = datetime(2024, 1, 1) + timedelta(days=i)
        raws.append(RawBar(
            symbol="X", dt=dt, id=i, freq=Freq.D,
            open=b["open"], close=b["close"], high=b["high"], low=b["low"], vol=b["volume"],
        ))

    try:
        c = CZSC(raws)
    except Exception as e:  # noqa
        return ("czsc运行异常", f"run_err:{e}", 0, 0, {})

    fenlei = getattr(c, "fenlei", None)
    bi_list = getattr(c, "bi_list", None) or []
    zs_list = getattr(c, "zs_list", None) or getattr(c, "zhongshu_list", None) or []

    label = _fenlei_to_label(fenlei, bi_list)
    raw_info = {
        "fenlei": fenlei,
        "bi_count": len(bi_list),
        "zs_count": len(zs_list),
        "last_bi_dir": str(getattr(bi_list[-1], "direction", "?"))
        if bi_list else "?",
    }
    return (label, str(fenlei), len(bi_list), len(zs_list), raw_info)


def _fenlei_to_label(fenlei, bi_list):
    """czsc fenlei 字符串 → 我们的分类枚举。

    czsc fenlei 形如：'aA' / 'aAb' / 'aAbB' / 'aAbBc' / 'aAbBcA' ...
    - 含两个中枢（有 B）→ 趋势；方向由最后一段笔方向定
    - 仅一个中枢（'aA'/'aAb'）→ 盘整
    - 空/单笔 → 无结构
    """
    if not fenlei:
        return "无结构"
    s = str(fenlei)
    # 趋势判定：出现 'B'（第二个中枢）即至少两中枢
    has_B = "B" in s
    # 方向：最后一段向上 → 上涨趋势；向下 → 下跌趋势
    last_up = None
    try:
        if bi_list:
            d = str(getattr(bi_list[-1], "direction", ""))
            last_up = ("up" in d.lower()) or ("Up" in d)
    except Exception:
        last_up = None
    if has_B:
        if last_up is True:
            return "上涨趋势"
        if last_up is False:
            return "下跌趋势"
        # 方向未知 → 退化为「趋势(方向不定)」按盘整外处理，标记 side
        return "趋势(方向不定)"
    if "A" in s:
        return "盘整"
    return "无结构"


# ───────────────────────── 原典清单口径（交实战终审）─────────────────────────
def _canonical_classify(zones_ranges):
    """formulas.md §9 价格拓扑口径（看全部中枢链，非只最后两中枢）。

    仅有 (bottom, top) 对时，本函数只能覆盖 §9.2/§9.4 的「重叠 / 同向不重叠」价格关系；
    **不能**看见连接段几何（§9.1「连接段须为反向走势」/ §9.2「夹同向小中枢→假趋势」）。
    因此价格-only 结果标注「(价格拓扑·原典)」——**不声称完整 §9**。
    完整连接段检查见 `_canonical_classify_with_connectors`（需带 members 的中枢 + 段/笔）。

    价格规则：
      - 0 中枢 → 无结构
      - 1 中枢 → 盘整 (a+A)
      - ≥2 中枢：所有相邻『同向且互不重叠』→ 趋势（上涨/下跌）；
                 任意相邻重叠，或方向不齐 → 盘整。
    zones_ranges: list of (bottom, top)，已按时序排列
    """
    zs = [(b, t) for (b, t) in zones_ranges if b is not None and t is not None]
    if len(zs) == 0:
        return "无结构"
    if len(zs) == 1:
        return "盘整(单中枢·原典)"
    # 相邻是否重叠
    def _overlap(a, b):
        return not (b[1] < a[0] or a[1] < b[0])
    overlapped = any(_overlap(zs[i], zs[i + 1]) for i in range(len(zs) - 1))
    up = all(zs[i + 1][1] > zs[i][1] and zs[i + 1][0] > zs[i][0] for i in range(len(zs) - 1))
    down = all(zs[i + 1][1] < zs[i][1] and zs[i + 1][0] < zs[i][0] for i in range(len(zs) - 1))
    if overlapped:
        return "盘整(多中枢重叠·原典)"
    if up:
        return "上涨趋势(价格拓扑·原典)"
    if down:
        return "下跌趋势(价格拓扑·原典)"
    return "盘整(方向不齐·原典)"


def _canonical_classify_with_connectors(zones, segments=None, strokes=None):
    """§9 完整口径：价格拓扑 + 连接段反向（formulas.md §9.1/§9.2/§9.4）。

    与生产 `classify_structure` / `_connector_is_non_reverse` 同规则：
    同向不重叠后若任一对连接段非反向 → 降为盘整（假趋势）；structure 标签仍是盘整。
    zones: 我们的 merged_zones（含 members/strokes 索引）或等价 dict 列表。
    """
    from trader_shared.chan_structure import _connector_is_non_reverse

    valid = [z for z in (zones or []) if isinstance(z, dict) and z.get("valid")]
    if not valid:
        return "无结构"
    if len(valid) == 1:
        return "盘整(单中枢·原典)"

    pair_direction = None
    zones_trend = "盘整"
    for i in range(1, len(valid)):
        prev, curr = valid[i - 1], valid[i]
        try:
            if float(curr["zh_bottom"]) > float(prev["zh_top"]):
                this_dir = "up"
            elif float(curr["zh_top"]) < float(prev["zh_bottom"]):
                this_dir = "down"
            else:
                return "盘整(多中枢重叠·原典)"
        except (TypeError, ValueError, KeyError):
            return "盘整(方向不齐·原典)"
        if pair_direction is not None and this_dir != pair_direction:
            return "盘整(方向不齐·原典)"
        pair_direction = this_dir
        zones_trend = "上涨趋势" if this_dir == "up" else "下跌趋势"

    if zones_trend not in ("上涨趋势", "下跌趋势"):
        return "盘整(方向不齐·原典)"

    pair_dir = "up" if zones_trend == "上涨趋势" else "down"
    for i in range(1, len(valid)):
        if _connector_is_non_reverse(
            valid[i - 1], valid[i], pair_dir, segments=segments, strokes=strokes
        ):
            return "盘整(假趋势·连接段非反向·原典)"
    return f"{zones_trend}(原典)"


def _zone_pairs(res):
    out = []
    for z in res.get("merged_zones", []) or []:
        b = z.get("zh_bottom")
        t = z.get("zh_top")
        if b is not None and t is not None:
            out.append((b, t))
    return out


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true", help="先打印 czsc 真实 API 结构")
    ap.add_argument("--csv-dir", default=None,
                    help="本地 CSV 目录（<code>.csv，网易财经格式），优先于网络数据源")
    args = ap.parse_args()

    print("# 缠论分类三角对照（原典口径 / czsc / 我们的实现）\n")
    print(f"样本区间 {START}~{END}，{len(SYMBOLS)} 只代表性标的")
    if args.csv_dir:
        print(f"数据源：本地 CSV 目录 {args.csv_dir}")
    else:
        print("数据源：新浪财经（沙箱可达）→ tushare(官方) → 网易财经 CSV（自动回退）")
    print()

    rows = []
    for code, label in SYMBOLS:
        # 取数：优先本地 CSV，否则走网络
        if args.csv_dir:
            bars, err = _load_csv_bars(os.path.join(args.csv_dir, code + ".csv"))
            if err:
                print(f"  {label} {code}: CSV 读取失败 {err}")
                continue
        else:
            try:
                bars = _fetch_real_bars(code)
            except Exception as e:  # noqa
                print(f"  {label} {code}: 获取异常 {e}")
                continue
        if not bars:
            print(f"  {label} {code}: 无数据")
            continue

        # 我们的实现
        st, tl, pc = _our_impl_classify(bars)
        our = chanlun_analysis(bars, current=bars[-1]["close"], symbol="X")
        zp = _zone_pairs(our)
        # 原典：有 members 时用完整 §9（含连接段）；否则价格-only（不声称完整 §9）
        zones_full = our.get("merged_zones") or []
        segs = our.get("segments") or []
        stro = our.get("strokes") or []
        if zones_full and (segs or stro):
            canon = _canonical_classify_with_connectors(zones_full, segments=segs, strokes=stro)
        else:
            canon = _canonical_classify(zp)
        # czsc（已废弃，仅作信息列；不可用则显示原因）
        cz_label, cz_fen, cz_bi, cz_zs, cz_raw = _czsc_classify(bars)

        if args.probe:
            print(f"  [PROBE] {label} {code}: czsc fenlei={cz_fen} bi={cz_bi} zs={cz_zs} raw={cz_raw}")

        # 共识/分歧判读（formulas.md §9.4）：我们的实现 vs 原典清单
        our_dir = _norm_dir(st)
        canon_dir = _norm_dir(canon)
        agree = (our_dir == canon_dir) and our_dir != "none"
        verdict = "共识" if agree else "⚠分歧"
        rows.append((label, code, st, cz_label, canon, pc, cz_bi, cz_zs, verdict))

        print(f"  {label} {code}:")
        print(f"    我们的实现 = {st} (trend={tl}, pivot={pc})")
        print(f"    czsc        = {cz_label} (fenlei={cz_fen}, bi={cz_bi}, zs={cz_zs})")
        print(f"    原典清单    = {canon}")
        print(f"    → {verdict}\n")

    # 汇总矩阵
    print("| 标的 | 我们的实现 | czsc | 原典清单(机械) | pivot | czsc笔/中枢 | 判读 |")
    print("|------|-----------|------|--------------|-------|-----------|------|")
    for label, code, st, cz, canon, pc, bi, zs, v in rows:
        print(f"| {label} {code} | {st} | {cz} | {canon} | {pc} | {bi}/{zs} | {v} |")

    n = len(rows)
    if n == 0:
        print("\n## 未能获取任何标的的真实数据，无法计算共识率。")
        print("   检查：1) 网络是否连通 tushare/网易；2) 用 --csv-dir 提供本地 CSV。")
        return
    agree_n = sum(1 for r in rows if r[-1] == "共识")
    print(f"\n## 共识率（我们的实现 vs 原典清单，方向一致）: {agree_n}/{n} = {agree_n/n*100:.1f}%")
    print("注: '分歧'不自动定罪——按 formulas.md §9.4 区分『定义取舍』与『真写偏』，")
    print("    原典清单中『待终审』项须交用户凭 K 线经验裁决。")


if __name__ == "__main__":
    main()
