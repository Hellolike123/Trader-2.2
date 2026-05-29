#!/usr/bin/env python3
"""
T0 盯盘 cron 入口 — 专门给 crontab 调用的单次检查。

特点（解决 shell 管道的 4 个隐患）：
1. 纯 Python 解析腾讯行情，不用 awk 拆 ~ 分隔文本
2. 非交易时间（周末/节假日/盘前盘后）直接静默退出，不发垃圾消息
3. 网络失败直接报错退出，不输出 0.00 触发的假低吸
4. 不依赖任何 LLM/模型，纯确定性代码

用法（crontab 每 5 分钟）：
  */5 9-14 * * 1-5  cd /path/to/project && python3 scripts/t0_cron.py --target 南网科技

多股轮询（选股池）：
  */5 9-14 * * 1-5  cd /path/to/project && python3 scripts/t0_cron.py --pool
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ── 1. 交易时间守卫 ──────────────────────────────────────────

def _is_trading_session() -> bool:
    """判断当前是否在交易时段内（周一到周五 9:30-15:00）。"""
    now = datetime.now()
    if now.weekday() >= 5:          # 周六/日
        return False
    t = now.hour * 100 + now.minute
    return 930 <= t <= 1500


# ── 2. 行情获取 ──────────────────────────────────────────────

def _fetch_live_price(name: str) -> tuple[float, float] | None:
    """用 light_data 拿实时行情，返回 (current_price, change_pct) 或 None。"""
    sys.path.insert(0, str(ROOT / "02-共享模块-shared" / "01-行情数据-market-data"))
    sys.path.insert(0, str(ROOT / "02-共享模块-shared"))

    from light_data import fetch_quote, HttpClient, resolve_security

    try:
        sec = resolve_security(name)
        http = HttpClient()
        q = fetch_quote(sec, http)
    except Exception:
        return None

    if q is None:
        return None

    try:
        price = float(q.get("current_price") or 0)
        chg = float(q.get("current_change_pct") or 0)
    except (TypeError, ValueError):
        return None

    if price <= 0:
        return None

    return price, chg


# ── 3. 选股池读取 ─────────────────────────────────────────────

def _load_pool_targets() -> list[str]:
    """读 ~/.trader/pool.json 获取活跃股票列表。"""
    pool_path = Path.home() / ".trader" / "pool.json"
    if not pool_path.exists():
        return []
    try:
        data = json.loads(pool_path.read_text(encoding="utf-8"))
        items = data.get("items", [])
        return [
            item["name"] for item in items
            if item.get("status") not in ("淘汰", "已退出")
        ]
    except Exception:
        return []


# ── 4. 价格区间读取（低吸位/支撑/防守）───────────────────────

def _load_price_zones(name: str) -> dict[str, float]:
    """从 pool.json 读这只票的预设价位。"""
    pool_path = Path.home() / ".trader" / "pool.json"
    if not pool_path.exists():
        return {}
    try:
        data = json.loads(pool_path.read_text(encoding="utf-8"))
        for item in data.get("items", []):
            if item.get("name") == name:
                return {
                    k: float(v) for k, v in item.items()
                    if k in ("trigger", "defense", "support", "current")
                       and isinstance(v, (int, float))
                }
    except Exception:
        pass
    return {}


# ── 5. 主逻辑 ─────────────────────────────────────────────────

def check_stock(name: str, verbose: bool = False) -> str | None:
    """检查单只股票，返回告警文本或 None。"""
    zones = _load_price_zones(name)
    quote = _fetch_live_price(name)
    if quote is None:
        if verbose:
            return f"[{name}] 行情获取失败，跳过"
        return None

    price, chg = quote
    trigger = zones.get("trigger")
    defense = zones.get("defense")

    alerts: list[str] = []
    if trigger and price >= trigger:
        alerts.append(f"到价 {trigger:.2f}")
    if defense and price <= defense:
        alerts.append(f"破防守 {defense:.2f}")

    if not alerts:
        return None

    chg_str = f"{chg:+.2f}%" if chg else ""
    return f"{name}  {price:.2f}  {chg_str}  |  {' / '.join(alerts)}"


def main() -> int:
    parser = argparse.ArgumentParser(description="T0 盯盘 cron 入口")
    parser.add_argument("--target", help="单只股票名称/代码")
    parser.add_argument("--pool", action="store_true", help="监控选股池所有活跃股票")
    parser.add_argument("--verbose", action="store_true", help="输出调试信息")
    args = parser.parse_args()

    # ── 交易时间守卫（核心 —— 避免节假日发垃圾消息）──
    if not _is_trading_session():
        if args.verbose:
            print("非交易时间，静默退出")
        return 0

    # ── 确定监控目标 ──
    if args.target:
        targets = [args.target]
    elif args.pool:
        targets = _load_pool_targets()
        if not targets:
            if args.verbose:
                print("选股池为空或无活跃股票")
            return 0
    else:
        parser.print_help()
        return 1

    # ── 逐股检查 ──
    results: list[str] = []
    for name in targets:
        alert = check_stock(name, verbose=args.verbose)
        if alert:
            results.append(alert)

    # ── 输出（无信号 = 完全静默，不发空消息）──
    if results:
        print("\n".join(results))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
