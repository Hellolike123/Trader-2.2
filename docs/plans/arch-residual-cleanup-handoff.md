# 架构余项收口（P1/P2）— Agent Handoff

> **状态**: mother_law（实现中）· 2026-08-02  
> **基线**: 伞分支 `cursor/arch-cleanup-complete-1c6b`（已含 #50/#51/#52）  
> **双 Agent**: 写落地 / 查对照；查完修完再 PR（建议 #53 伞 PR，并关闭重复的 #50–#52）。

---

## 0. 法源

1. `resonance-and-orchestration.md` §1 / §6 阶段4：fusion 仅仪表；主叙事跟 decision_view。  
2. `analysis-strategy-boundaries.md` §0：禁止从 fusion.action 直接推断出手。  
3. `ARCHITECTURE.md` §5.1：数据 SSOT = `get_provider`；builder 勿再堆无关 DI。  
4. `docs/audit/p0-batch-1-report.md` / decision_core：置信度「超过阈值」= 严格 `>`。  
5. 已落地：`signal-fusion-override-gate` / `pool-quote-provider` / `fusion-no-silent-classic`。

---

## 1. 必须（本 PR 余项）

| ID | 项 |
|----|-----|
| R1 | `test_arch_boundaries`（或同文件）：静态/AST 断言 `signal_core.build_signal` 调用 `_map_fusion_to_signal` 前须检查 `FUSION_OVERRIDE_ENABLED`（锁 #50 M6） |
| R2 | `t0_candidate_core`：`fc >= FUSION_CONFIDENCE_THRESHOLD` → 严格 `>`（对齐 decision_core / signal_core）；补边界测 |
| R3 | `report_builder`：去掉无用的 `TencentFetcher()` 注入；下游若仍接 `fetcher` 参数可传 `None` / 保留签名，禁止再构造死 DI；测不破 |
| R4 | `fusion_stage._attach_fusion_verbatim`：改为**仪表文案**（分数/regime/分歧 +「仅参考」），禁止 `🎯 {action}` 指令形主行；字段仍存在；不改加权分 |
| R5 | `stage_context.py`：文档化 bag 关键字段（docstring 清单即可；可选 `TypedDict` total=False 不强制全管线 mypy） |
| R6 | 相关 pytest 绿；门禁不红 |

---

## 2. 禁止

1. 不删 `fusion_classic_mappers`；不改 DV/池分道/出手铁律。  
2. 不拆 `wyckoff_events` / `light_data` / `short_midline`（无拆缝手递）。  
3. 不改 A2（merge 挪到 DV 后）。  
4. 不重开报告四区；不改 golden 骨架（verbatim 默认不展示时尤勿动 golden）。  
5. 不默认打开 `FUSION_OVERRIDE` / enrich boards。  
6. 不改 `build_daily_ruling` 用 action 收紧「不宜追高」的产品语义（需另开产品手递）。

---

## 3. 可改白名单

- `tests/test_arch_boundaries.py`  
- `trader_shared/t0_candidate_core.py` + 相关测  
- `trader_shared/report_builder.py`（及仅因去 fetcher 而必须的 stage 签名兼容）  
- `trader_shared/report_pipeline/fusion_stage.py`  
- `trader_shared/report_pipeline/stage_context.py`  
- 可选：`01-功能包-packages/trader/references/fusion-guide.md` 一句仪表化  
- 本文手递  

---

## 4. 验收

| ID | 项 |
|----|-----|
| A1 | arch 测失败于「无闸 remap」假实现（或源码结构断言通过） |
| A2 | t0：`fc == threshold` 且 override 开 → 不覆盖 |
| A3 | builder 源码无 `TencentFetcher()` |
| A4 | verbatim 不含 `🎯` 动作主行；仍写 `fusion_verbatim` |
| A5 | StageContext 文档列出关键键 |
| A6 | 查 Agent PASS；门禁绿 |

---

## 5. 明确不做（本轮结束声明）

| 项 | 原因 |
|----|------|
| 删除 classic 模式 / mappers | #52 手递禁止；裁决 DEFER |
| wyckoff_events / light_data 巨石拆分 | 无拆缝手递；母法源只授权语义改 |
| StageContext 全管线严格 TypedDict | 过大；本轮只文档化 |
| daily_ruling 去 action | 需产品手递 |

写完本余项 + #50–#52 伞合入后，架构评审「可立即落地」清单视为收口。
