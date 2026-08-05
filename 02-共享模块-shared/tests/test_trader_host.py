"""TRADER_HOST / 资金流选源 / get_provider 强制 env。"""
from __future__ import annotations

import json

import trader_shared.data_provider as dp
from trader_shared.trader_host import (
    HOST_HERMES,
    HOST_LOCAL,
    HOST_WORKBUDDY,
    detect_trader_host,
    fund_flow_source_order,
)


def test_detect_host_env_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("TRADER_HOST", "workbuddy")
    monkeypatch.setattr(
        "trader_shared.trader_host.workbuddy_connectors_present", lambda: False
    )
    assert detect_trader_host() == HOST_WORKBUDDY
    monkeypatch.setenv("TRADER_HOST", "local")
    assert detect_trader_host() == HOST_LOCAL


def test_detect_host_from_connectors(monkeypatch):
    monkeypatch.delenv("TRADER_HOST", raising=False)
    monkeypatch.setattr(
        "trader_shared.trader_host._host_from_skill_config", lambda: ""
    )
    monkeypatch.setattr(
        "trader_shared.trader_host.workbuddy_connectors_present", lambda: True
    )
    assert detect_trader_host() == HOST_WORKBUDDY
    monkeypatch.setattr(
        "trader_shared.trader_host.workbuddy_connectors_present", lambda: False
    )
    assert detect_trader_host() == HOST_HERMES


def test_fund_flow_order_by_host(monkeypatch):
    monkeypatch.setenv("TRADER_HOST", "workbuddy")
    order_wb = fund_flow_source_order()
    assert order_wb[0] == "tdx"
    assert order_wb == ["tdx", "tushare", "sina"]
    monkeypatch.setenv("TRADER_HOST", "hermes")
    order_hm = fund_flow_source_order()
    assert order_hm[0] == "tushare"
    assert order_hm == ["tushare", "tdx", "sina"]


def test_get_provider_forced_env_beats_tushare(monkeypatch):
    """有 token 时 TRADER_DATA_PROVIDER 仍必须生效。"""
    dp.clear_provider()
    monkeypatch.setenv("TRADER_DATA_PROVIDER", "tencent")
    monkeypatch.setattr(dp, "_tushare_available", lambda: True)
    p = dp.get_provider()
    assert isinstance(p, dp.UnifiedProvider)
    assert p.name == "tencent"
    dp.clear_provider()


def test_get_provider_workbuddy_without_tushare_uses_mootdx(monkeypatch):
    dp.clear_provider()
    monkeypatch.delenv("TRADER_DATA_PROVIDER", raising=False)
    monkeypatch.setenv("TRADER_HOST", "workbuddy")
    monkeypatch.setattr(dp, "_tushare_available", lambda: False)
    p = dp.get_provider()
    assert isinstance(p, dp.UnifiedProvider)
    assert p.name == "mootdx"
    dp.clear_provider()


def test_get_provider_hermes_without_tushare_uses_tencent(monkeypatch):
    dp.clear_provider()
    monkeypatch.delenv("TRADER_DATA_PROVIDER", raising=False)
    monkeypatch.setenv("TRADER_HOST", "hermes")
    monkeypatch.setattr(dp, "_tushare_available", lambda: False)
    p = dp.get_provider()
    assert isinstance(p, dp.UnifiedProvider)
    assert p.name == "tencent"
    dp.clear_provider()


def test_absent_config_host_allows_connector_detect(monkeypatch):
    """未 stamp trader_host 时，connectors 探测才能生效。"""
    monkeypatch.delenv("TRADER_HOST", raising=False)
    monkeypatch.setattr(
        "trader_shared.trader_host._host_from_skill_config", lambda: ""
    )
    monkeypatch.setattr(
        "trader_shared.trader_host.workbuddy_connectors_present", lambda: True
    )
    assert detect_trader_host() == HOST_WORKBUDDY
    assert fund_flow_source_order()[0] == "tdx"


def test_host_from_config_json(monkeypatch, tmp_path):
    monkeypatch.delenv("TRADER_HOST", raising=False)
    skill_root = tmp_path
    (skill_root / "config.json").write_text(
        json.dumps({"trader_host": "workbuddy"}), encoding="utf-8"
    )
    fake = skill_root / "scripts" / "trader_shared" / "trader_host.py"
    fake.parent.mkdir(parents=True)
    fake.write_text("# stub\n", encoding="utf-8")
    import trader_shared.trader_host as th

    monkeypatch.setattr(th, "__file__", str(fake))
    monkeypatch.setattr(th, "workbuddy_connectors_present", lambda: False)
    assert th.detect_trader_host() == HOST_WORKBUDDY
