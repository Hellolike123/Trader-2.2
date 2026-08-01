"""账户级风控模块（Account Risk Control）

用户手动输入账户数据，系统自动检查风控规则。

用法:
    from account_risk import AccountRisk
    risk = AccountRisk()
    risk.update_balance(1000000)  # 初始账户 100 万
    risk.record_trade("南网科技", "buy", 1000, 57.50)
    status = risk.check_risk()
"""

from __future__ import annotations

import json
from datetime import datetime, date
from pathlib import Path
from typing import Any

from trader_shared.trader_paths import KeyedPath

_ACCOUNT_FILE = KeyedPath("account")


class AccountRisk:
    """账户级风控管理器。"""

    def __init__(self) -> None:
        self._data = self._load()

    def _load(self) -> dict[str, Any]:
        try:
            if _ACCOUNT_FILE.exists():
                return json.loads(_ACCOUNT_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {
            "balance": 0.0,         # 当前账户总值
            "initial_balance": 0.0,  # 初始账户总值
            "trades": [],            # 交易记录
            "daily_pnl": {},         # 每日盈亏 {date: pnl}
            "weekly_pnl": {},        # 每周盈亏 {week: pnl}
            "highest_balance": 0.0,  # 历史最高账户总值
        }

    def _save(self) -> None:
        try:
            _ACCOUNT_FILE.parent.mkdir(parents=True, exist_ok=True)
            _ACCOUNT_FILE.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def update_balance(self, balance: float) -> None:
        """更新当前账户总值。"""
        self._data["balance"] = balance
        if self._data["initial_balance"] == 0:
            self._data["initial_balance"] = balance
        if balance > self._data.get("highest_balance", 0):
            self._data["highest_balance"] = balance
        self._save()

    def record_trade(self, stock: str, action: str, shares: int, price: float) -> None:
        """记录一笔交易。"""
        trade = {
            "stock": stock,
            "action": action,  # "buy" or "sell"
            "shares": shares,
            "price": price,
            "time": datetime.now().isoformat(timespec="seconds"),
        }
        self._data["trades"].append(trade)

        # 更新每日盈亏
        today = date.today().isoformat()
        # 简化：用买卖差价估算当日盈亏
        if action == "sell":
            # 找最近的同股票买入
            for t in reversed(self._data["trades"][:-1]):
                if t["stock"] == stock and t["action"] == "buy":
                    pnl = (price - t["price"]) * shares
                    self._data["daily_pnl"][today] = self._data["daily_pnl"].get(today, 0) + pnl
                    break

        self._save()

    def check_risk(self) -> dict[str, Any]:
        """检查账户级风控规则。

        Returns:
            {
                "status": "正常" / "触发",
                "daily_pnl_pct": float,
                "weekly_pnl_pct": float,
                "drawdown_pct": float,
                "alerts": list[str],
                "display": str,  # 格式化显示
            }
        """
        balance = self._data.get("balance", 0)
        initial = self._data.get("initial_balance", 0)
        highest = self._data.get("highest_balance", 0)

        if balance <= 0 or initial <= 0:
            return {
                "status": "未知",
                "daily_pnl_pct": 0,
                "weekly_pnl_pct": 0,
                "drawdown_pct": 0,
                "alerts": ["账户数据未初始化"],
                "display": "💰 账户风控 ｜ 数据未初始化",
            }

        # 当日盈亏
        today = date.today().isoformat()
        daily_pnl = self._data.get("daily_pnl", {}).get(today, 0)
        daily_pnl_pct = (daily_pnl / balance) * 100

        # 本周盈亏
        week_key = date.today().strftime("%Y-W%W")
        weekly_pnl = 0
        for d, pnl in self._data.get("daily_pnl", {}).items():
            if d.startswith(date.today().strftime("%Y")):  # 简化：同一年
                weekly_pnl += pnl
        weekly_pnl_pct = (weekly_pnl / balance) * 100

        # 回撤
        if highest > 0:
            drawdown_pct = ((highest - balance) / highest) * 100
        else:
            drawdown_pct = 0

        # 风控检查
        alerts: list[str] = []
        if daily_pnl_pct < -1.5:
            alerts.append(f"当日亏损 {daily_pnl_pct:.1f}% > 1.5%，停止操作")
        if weekly_pnl_pct < -3:
            alerts.append(f"本周亏损 {weekly_pnl_pct:.1f}% > 3%，下周仓位减半")
        if drawdown_pct > 10:
            alerts.append(f"累计回撤 {drawdown_pct:.1f}% > 10%，全面降仓至30%")

        status = "触发" if alerts else "正常"

        # 格式化显示
        daily_icon = "✅" if daily_pnl_pct >= 0 else "⚠️" if daily_pnl_pct >= -1.5 else "❌"
        weekly_icon = "✅" if weekly_pnl_pct >= 0 else "⚠️" if weekly_pnl_pct >= -3 else "❌"
        dd_icon = "✅" if drawdown_pct <= 5 else "⚠️" if drawdown_pct <= 10 else "❌"

        display = (
            f"💰 账户风控 ｜ "
            f"当日 {daily_pnl_pct:+.1f}% {daily_icon} ｜ "
            f"本周 {weekly_pnl_pct:+.1f}% {weekly_icon} ｜ "
            f"回撤 -{drawdown_pct:.1f}% {dd_icon}"
        )

        if alerts:
            display = f"🚨 账户风控 ｜ " + " ｜ ".join(alerts)

        return {
            "status": status,
            "daily_pnl_pct": round(daily_pnl_pct, 2),
            "weekly_pnl_pct": round(weekly_pnl_pct, 2),
            "drawdown_pct": round(drawdown_pct, 2),
            "alerts": alerts,
            "display": display,
        }
