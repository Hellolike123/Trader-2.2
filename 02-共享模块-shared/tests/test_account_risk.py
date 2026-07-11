"""account_risk 模块测试。"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

for mod in ("trader_shared.account_risk",):
    if mod in sys.modules:
        del sys.modules[mod]

from trader_shared.account_risk import AccountRisk, _ACCOUNT_FILE


def _make_risk(tmp_path: Path) -> AccountRisk:
    """创建一个使用临时文件的 AccountRisk 实例。"""
    with patch("trader_shared.account_risk._ACCOUNT_FILE", tmp_path / "account.json"):
        return AccountRisk()


class TestAccountRiskInit:
    def test_init_creates_default_data(self, tmp_path):
        risk = _make_risk(tmp_path)
        assert risk._data["balance"] == 0.0
        assert risk._data["initial_balance"] == 0.0
        assert risk._data["trades"] == []
        assert risk._data["daily_pnl"] == {}


class TestUpdateBalance:
    def test_sets_balance(self, tmp_path):
        risk = _make_risk(tmp_path)
        risk.update_balance(100000)
        assert risk._data["balance"] == 100000

    def test_sets_initial_on_first_call(self, tmp_path):
        risk = _make_risk(tmp_path)
        risk.update_balance(100000)
        assert risk._data["initial_balance"] == 100000

    def test_does_not_overwrite_initial(self, tmp_path):
        risk = _make_risk(tmp_path)
        risk.update_balance(100000)
        risk.update_balance(200000)
        assert risk._data["initial_balance"] == 100000

    def test_updates_highest(self, tmp_path):
        risk = _make_risk(tmp_path)
        risk.update_balance(100000)
        risk.update_balance(150000)
        assert risk._data["highest_balance"] == 150000
        risk.update_balance(120000)
        assert risk._data["highest_balance"] == 150000


class TestRecordTrade:
    def test_buy_records_trade(self, tmp_path):
        risk = _make_risk(tmp_path)
        risk.record_trade("TEST", "buy", 100, 10.0)
        assert len(risk._data["trades"]) == 1
        assert risk._data["trades"][0]["stock"] == "TEST"
        assert risk._data["trades"][0]["action"] == "buy"

    def test_sell_calculates_pnl(self, tmp_path):
        risk = _make_risk(tmp_path)
        risk.record_trade("TEST", "buy", 100, 10.0)
        risk.record_trade("TEST", "sell", 100, 12.0)
        today = __import__("datetime").date.today().isoformat()
        assert risk._data["daily_pnl"][today] == 200.0  # (12-10)*100

    def test_sell_loss(self, tmp_path):
        risk = _make_risk(tmp_path)
        risk.record_trade("TEST", "buy", 100, 10.0)
        risk.record_trade("TEST", "sell", 100, 8.0)
        today = __import__("datetime").date.today().isoformat()
        assert risk._data["daily_pnl"][today] == -200.0


class TestCheckRisk:
    def test_uninitialized_account(self, tmp_path):
        risk = _make_risk(tmp_path)
        result = risk.check_risk()
        assert result["status"] == "未知"
        assert "账户数据未初始化" in result["alerts"]

    def test_normal_status(self, tmp_path):
        risk = _make_risk(tmp_path)
        risk.update_balance(100000)
        result = risk.check_risk()
        assert result["status"] == "正常"
        assert result["alerts"] == []

    def test_daily_loss_alert(self, tmp_path):
        risk = _make_risk(tmp_path)
        risk.update_balance(100000)
        # Record a loss that exceeds 1.5%
        risk._data["daily_pnl"][__import__("datetime").date.today().isoformat()] = -2000
        result = risk.check_risk()
        assert result["status"] == "触发"
        assert any("当日亏损" in a for a in result["alerts"])

    def test_drawdown_alert(self, tmp_path):
        risk = _make_risk(tmp_path)
        risk.update_balance(100000)
        risk._data["highest_balance"] = 120000
        risk._data["balance"] = 105000  # ~12.5% drawdown from 120k
        result = risk.check_risk()
        assert result["status"] == "触发"
        assert any("回撤" in a for a in result["alerts"])

    def test_display_format(self, tmp_path):
        risk = _make_risk(tmp_path)
        risk.update_balance(100000)
        result = risk.check_risk()
        assert "💰 账户风控" in result["display"]
        assert "当日" in result["display"]
        assert "回撤" in result["display"]
