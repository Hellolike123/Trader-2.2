# Goal: 双宿主取数分流 — COMPLETE / SHIP

## Done
- `trader_host.py`：TRADER_HOST / config / connectors 探测
- `get_provider`：强制 env 优先；hermes/workbuddy 回落
- 资金流 auto：workbuddy → tdx 先
- pack_all：仅显式 TRADER_HOST 才 stamp（不掐死探测）
- 双 Agent 审 bug → 修 2 项 P1 → 复审 SHIP

## Verify
- pytest trader_host + TestGetProviderTushare：绿
- 烟测：hermes fund=tushare 先；workbuddy fund=tdx 先；报告 exit 0
