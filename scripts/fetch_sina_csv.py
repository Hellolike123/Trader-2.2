#!/usr/bin/env python3
"""预拉取 7 只标的新浪日线，存为本地 CSV（网易财经格式，供 --csv-dir 离线诊断）。

彻底绕开新浪接口的偶发限流：一次拿全、落盘、可复现。
用法（沙箱需放行新浪，已验证可达）：
  PYTHONPATH=02-共享模块-shared:01-功能包-packages/trader/scripts \\
    python scripts/fetch_sina_csv.py
"""
import os
import csv
import time
import requests

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "chan_csv")
os.makedirs(OUT, exist_ok=True)

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


def _sina_symbol(code):
    num, market = code.split(".")
    return ("sh" if market == "SH" else "sz") + num


def main():
    for code, label in SYMBOLS:
        sym = _sina_symbol(code)
        url = ("https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
               f"CN_MarketData.getKLineData?symbol={sym}&scale=240&ma=no&datalen=1500")
        rows = None
        for attempt in range(5):
            try:
                r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
                rows = r.json()
                break
            except Exception as e:  # noqa
                print(f"  {label} {code} 重试{attempt + 1}: {e}")
                time.sleep(1.5)
        if not rows:
            print(f"  {label} {code}: 拉取失败，跳过")
            continue
        path = os.path.join(OUT, code + ".csv")
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["日期", "开盘价", "收盘价", "最高价", "最低价", "成交量"])
            n = 0
            for d in rows:
                dt = str(d.get("day", "")).replace("-", "")
                if dt < START or dt > END:
                    continue
                w.writerow([dt, d["open"], d["close"], d["high"], d["low"], d["volume"]])
                n += 1
        print(f"  {label} {code}: 存 {path} ({n} 交易日)")
    print("done ->", OUT)


if __name__ == "__main__":
    main()
