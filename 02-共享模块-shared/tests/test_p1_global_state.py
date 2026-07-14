"""P1 全局状态收敛回归：消除运行时 os.environ 写入副作用。

覆盖：
- data_provider.set_provider 不再回写 os.environ（消隐全局副作用，并行/测试可复现）
- tushare_client.query_realtime 的 NO_PROXY 切换：正常/异常路径下 os.environ 零残留

均为离线测试（用 MagicMock 注入 fake tushare，不触发任何网络），可进 CI 门禁。
"""
from __future__ import annotations

import os
import sys
import types
from unittest.mock import MagicMock

import trader_shared.data_provider as data_provider
import trader_shared.tushare_client as tushare_client


# ── data_provider: set_provider 不再写 env ────────────────────────────────

def test_set_provider_does_not_write_env(monkeypatch):
    """set_provider 只设置模块级 _provider 单例，绝不回写 os.environ。"""
    monkeypatch.delenv("TRADER_DATA_PROVIDER", raising=False)
    orig = data_provider._provider
    try:
        fake = types.SimpleNamespace(name="fake")
        data_provider.set_provider(fake)
        # 关键断言：env 不应被回写（原代码会写 os.environ["TRADER_DATA_PROVIDER"]）
        assert "TRADER_DATA_PROVIDER" not in os.environ
        # get_provider 优先返回已设置的实例（不再依赖 env 回读）
        assert data_provider.get_provider() is fake
    finally:
        data_provider._provider = orig


def test_set_provider_overrides_env_fallback_without_mutating_env(monkeypatch):
    """即使 env 指向别的源，set_provider 后 get_provider 仍返回设置的实例，且 env 原值不动。"""
    monkeypatch.setenv("TRADER_DATA_PROVIDER", "tencent")
    orig = data_provider._provider
    try:
        fake = types.SimpleNamespace(name="myprovider")
        data_provider.set_provider(fake)
        assert data_provider.get_provider() is fake
        # env 原值未被改动（无全局副作用）
        assert os.environ.get("TRADER_DATA_PROVIDER") == "tencent"
    finally:
        data_provider._provider = orig


# ── tushare: NO_PROXY 切换零残留（并发锁 + 还原） ──────────────────────────

def _make_client(monkeypatch):
    """构造一个可用、但完全走 fake tushare 的 TushareClient，避免任何网络。"""
    fake_ts = MagicMock()
    fake_stock = MagicMock()
    fake_cons = MagicMock()
    fake_stock.cons = fake_cons
    fake_ts.stock = fake_stock
    monkeypatch.setitem(sys.modules, "tushare", fake_ts)
    monkeypatch.setitem(sys.modules, "tushare.stock", fake_stock)

    client = tushare_client.TushareClient()
    client._token = "fake"
    client._sdk_ok = True
    client._rate_limit = lambda: None  # 跳过限流 sleep，保持测试确定性
    return client, fake_ts


def test_tushare_no_proxy_no_leak_on_success(monkeypatch):
    """正常路径：调用结束后 os.environ['NO_PROXY'] 必须还原为调用前状态。"""
    client, fake_ts = _make_client(monkeypatch)
    fake_df = MagicMock()
    fake_df.to_dict.return_value = [{"code": "688248.SH", "price": 10.0}]
    fake_df.__len__.return_value = 1  # 让 len(df) > 0，走 to_dict 分支
    fake_ts.realtime_quote.return_value = fake_df

    before = os.environ.get("NO_PROXY")
    result = client.query_realtime("688248.SH")
    after = os.environ.get("NO_PROXY")

    assert after == before, "调用结束后 NO_PROXY 必须还原为调用前状态（无全局残留）"
    assert result == [{"code": "688248.SH", "price": 10.0}]


def test_tushare_no_proxy_no_leak_on_exception(monkeypatch):
    """异常路径：即便 realtime_quote 抛错，NO_PROXY 仍须被 finally 还原。"""
    client, fake_ts = _make_client(monkeypatch)
    fake_ts.realtime_quote.side_effect = RuntimeError("boom")  # 触发异常路径

    before = os.environ.get("NO_PROXY")
    result = client.query_realtime("688248.SH")
    after = os.environ.get("NO_PROXY")

    # 异常被外层 except 吞掉返回 []
    assert result == []
    # 即便异常，NO_PROXY 仍须还原（finally 保证，否则会污染后续调用/测试）
    assert after == before, "异常路径下 NO_PROXY 必须还原"
