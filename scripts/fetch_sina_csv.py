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
    ("688248.SH", "南网科技(科创)"),
    ("600519.SH", "贵州茅台(消费权重)"),
    ("000001.SZ", "平安银行(银行低波)"),
    ("300750.SZ", "宁德时代(新能源高波)"),
    ("002050.SZ", "三花智控(机械)"),
    ("600036.SH", "招商银行(银行)"),
    ("000858.SZ", "五粮液(消费)"),
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
