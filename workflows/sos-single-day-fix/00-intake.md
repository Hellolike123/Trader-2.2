# Intake — Wyckoff SOS 单日爆发型漏判

| 项 | 记录 |
|----|------|
| 一句话请求 | 修复 `_detect_sos` 只认「5 日 ≥4 阳爬坡」而漏掉「放量大阳站上 TR 上沿」的单日爆发型 SOS |
| 仓库 | `/Users/like/Documents/Opencode/Trader3.0` |
| 敏感面 | 无生产 DB / 无服务重启 / 无公网路由；纯检测逻辑 + 测例 |
| 法源入口 | WorkBuddy 交接：`/Users/like/Documents/Workbuddy/Docs/wyckoff-sos-修复交接说明.md`；仓内 `docs/audit/wyckoff-original-concept-inventory.md` §三 SOS；AGENTS.md 威科夫锚点 |
| 引擎真相 | `02-共享模块-shared/trader_shared/wyckoff_events.py` → `_detect_sos`（约 L1720+） |
| 配置 | `02-共享模块-shared/trader_shared/config.py`（`WYCKOFF_DIVERGENCE_BARS` 等；**尚无**单日 SOS 常量） |
| 测试 | `02-共享模块-shared/tests/test_wyckoff_core.py`（已 import `_detect_sos`；缺单日分支边界测） |
| 调用链 | `wyckoff_core` 主分析；事件簇 `_scan_last_event(..., _detect_sos)`；`_detect_backup` 回扫；JAC 依赖 SOS 背景 |
| git 基线 | **未取到**（本会话 bash 被拒）；实现前 sole-writer 必须补 `git status --short --branch` |
| roster 探测 | **未取到** `discover-roster.py --probe`（bash 拒）；见 `01-roster-proposal.md` |
| 任务分级 | **Medium**（行为变更 + 集成风险：簇/BU/JAC/打分；可逆；无 data/service/destructive） |
| 工作流 | 书面计划 → **人批** → sole-writer 实现 → 独立 review → 验证 → 终报（signoff 包按需） |

## 已核实代码事实（research，只读）

1. `_detect_sos` docstring/实现均为「连续放量突破」：≥4/5 阳 + 总体抬高 + 均量×1.2 + 累计涨≥2%。
2. `tr_ctx` 仅用 `tr_baseline_volume`；**不用** `tr_upper`。
3. 3/5 阳时直接 `sos_reason: 仅 3/5 阳线，不足 4 根` —— 与南网案例一致。
4. JAC（`_detect_jump_across_creek`）要求 `sos_signal | bu | markup`，**不能**兜单日突破。
5. 交接文档 §7 改路径写成 skill 包内 `trader_shared` —— **错误**；应按 AGENTS 改 shared 引擎。

## 未知 / 待实现前补

- [ ] 当前分支是否脏、是否已有并行威科夫改动
- [ ] 机器上 codex/claude 健康态（reviewer 跨厂商）
- [ ] 南网 688248 在本机行情源下 TR 上沿是否仍约 44.50（集成冒烟用；单测不依赖外网）
