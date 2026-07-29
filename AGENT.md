# AGENT.md — 已降级（勿当主入口）

改代码 / 接任务请先读：

1. [`AGENTS.md`](AGENTS.md) — 含「改代码去哪」
2. [`docs/designs/resonance-and-orchestration.md`](docs/designs/resonance-and-orchestration.md) — 五层+编排法源
3. 按需 [`AGENTS_DEEP.md`](AGENTS_DEEP.md)

冲突时以 `AGENTS.md` + `trader_shared/` 实现为准。

历史长文已移除，避免误导去改 monolith `final_pool.py` 或 skill 包内引擎副本（现为 identity shim）。
