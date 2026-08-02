# Skill 使用指南补齐 chanlun — Agent Handoff

> **状态**: done（2026-08-02）  

> **产品裁决**: 文档/指南层；**不改**引擎与面板渲染。  
> **背景**: draft PR #3 仅四 Skill；`chanlun` 专项卡已合（#29），指南须跟上，避免 Agent/操盘手漏岗。

---

## 1. 必须（S-U1…S-U6）

| ID | 必须 |
|----|------|
| S-U1 | `docs/guide/skill-usage.md` 主 Skill 表含 **chanlun**（结构学术卡；不下单；不覆盖周线威科夫阶段） |
| S-U2 | 入口命令：`01-功能包-packages/chanlun/scripts/final_chanlun.py --target <NAME>`（及包内等价） |
| S-U3 | 一天节奏里标明：搞不清笔/买卖点依据时用 chanlun；吸筹/派发用 wyckoff；二者都不当总司令 |
| S-U4 | `README.md` / `AGENTS.md` / `docs/README.md` / `user-guide.md` 有指南入口（可复用 PR #3 挂链；须指向现行文件） |
| S-U5 | 指南正文遵守仓库文档习惯；**勿**教用户用旧 `🎯`+`📍 决策` 当主输出；强调跑脚本贴面板 |
| S-U6 | 注明 `chanlun` 关心点：取数 / 期限 / 一二三买只跟引擎 / 笔方向（可链到 `chanlun-skill-playbook.md` 或 deep-card handoff） |

---

## 2. 禁止

1. 不改 `trader_shared` 业务代码（本 PR 纯文档，除非另开手递）。  
2. 不写「宜买/可执行/可低吸」操作指令。  
3. 不把 chanlun 写成中线阶段定论岗。  
4. 不重开报告四区。

---

## 3. 可改 / 勿改

| 可改 | 勿改 |
|------|------|
| `docs/guide/skill-usage.md`（新建或基于 #3 改写） | 任意引擎 / 测例（本 PR） |
| `README.md` / `AGENTS.md` / `docs/README.md` / `docs/guide/user-guide.md`（仅挂链/一句） | Skill 包引擎 shim 正文 |
| 本 handoff；可将 `chanlun-cd-followup` / deep-card §10.2 标 done/stale 指针 | fusion / 出手 |

---

## 4. 验收

| ID | 项 |
|----|-----|
| M-S1 | 打开 skill-usage.md 能找到 chanlun 岗与命令 |
| M-S2 | 挂链文档可点到该指南 |
| M-S3 | diff 无业务 `.py`（本 PR） |
| M-S4 | 查 Agent 对照 S-U* PASS |

---

## 5. 双 Agent

- **写 Agent**：按 S-U* 写文档 + commit/push。  
- **查 Agent**：对照本文；禁夹带引擎改动。

---

## 附：同轮可选（另 commit 可接受）

若写 Agent 有余力且**不扩业务范围**：在 `chanlun-cd-followup-handoff.md` 文首标 `status: done`，并在 `chanlun-skill-deep-card-handoff.md` §10.2 加一句「后续见 follow-up DoD / PR #29，表内 ❌ 为历史快照」。
