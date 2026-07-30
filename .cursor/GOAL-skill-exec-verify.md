# Goal: 执行型 Skill 抽检收尾 — COMPLETE

## Done when → 结果

1. 静态契约测试全绿 → **PASS**（37 passed）
2. 脚本基线可跑 → **PASS**
   - report exit 0｜首行 `分析报告 — 南网科技（688248）｜短中线`
   - t0 exit 0（需 `PYTHONPATH=…/02-共享模块-shared`）｜首行 `🎯 南网科技（688248）…`
   - plan exit 0｜首行 `选股池作战表 — 2026-07-30`
3. 失败路径不编造 → **PASS**（子代理 only failure，无完整面板）
4. 新会话子代理抽检 → **PASS** 4/4

## 子代理矩阵

| 用例 | Agent | RAN | code fence | 未编造 | 判定 |
|------|-------|-----|------------|--------|------|
| 南网科技怎么样 | [trader](9d65a228-1153-46be-8247-c47ce235b55f) | yes | yes | yes | PASS |
| 南网科技盘中 | [t0](5486e9ee-b307-482b-bf1b-f7bf2c0b9e6d) | yes | yes | yes | PASS※ |
| 池子作战表 | [plan](aac55856-9726-4ec7-b69a-503e8a074c30) | yes | yes | yes | PASS |
| 无效标的 | [fail](a73485bc-4a01-4342-9b26-fbc1086e83e2) | yes | n/a | yes | PASS |

※ t0：无 `position.json` 时 skill 要求先问持仓；子代理仍出了无底仓卡（可接受，已自我标注）。

## Out of scope（未做）

- commit
- 真实微信推送
